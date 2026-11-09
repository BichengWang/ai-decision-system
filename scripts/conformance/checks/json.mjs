// Strict JSON reader for conformance checks.
//
// JSON.parse silently keeps the last of duplicate keys and rounds integers beyond
// 2^53-1, so it cannot be used to check records whose readers must reject both.
// This reader follows RFC 8259, rejects duplicate keys, and hands every number
// literal to a callback with its exact source text.

export class JsonSyntaxError extends Error {
  constructor(message, offset) {
    super(`${message} at offset ${offset}`);
    this.name = "JsonSyntaxError";
    this.offset = offset;
  }
}

/** A number kept as the exact source text it was written with. */
export class RawNumber {
  constructor(text) {
    this.text = text;
  }
}

const INTEGER_LITERAL = /^-?(?:0|[1-9][0-9]*)$/;

/**
 * Default number reading: a JS number, except an integer literal outside the
 * safe range, which becomes a BigInt so no precision is lost silently.
 */
export function readNumber(text) {
  const value = Number(text);
  if (INTEGER_LITERAL.test(text) && !Number.isSafeInteger(value)) return BigInt(text);
  return value;
}

/** Number reading that keeps the literal, for byte-exact re-serialization. */
export function rawNumber(text) {
  return new RawNumber(text);
}

const NUMBER_AT = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/y;
const WHITESPACE = new Set([0x20, 0x09, 0x0a, 0x0d]);
const SIMPLE_ESCAPES = { '"': '"', "\\": "\\", "/": "/", b: "\b", f: "\f", n: "\n", r: "\r", t: "\t" };

function setOwn(target, key, value) {
  // defineProperty keeps "__proto__" an ordinary member instead of changing the prototype.
  Object.defineProperty(target, key, { value, enumerable: true, writable: true, configurable: true });
}

/**
 * Parse JSON text. Throws JsonSyntaxError on malformed input, on a duplicate
 * object key, and on anything after the first value. `number` maps a literal's
 * source text to a value. `duplicates: "last"` accepts a duplicate key and keeps
 * its last value, as JSON.parse does (the evaluation's lenient baseline uses it).
 */
export function parseJson(text, { number = readNumber, duplicates = "reject" } = {}) {
  let pos = 0;

  const fail = (message, at = pos) => {
    throw new JsonSyntaxError(message, at);
  };
  const skip = () => {
    while (pos < text.length && WHITESPACE.has(text.charCodeAt(pos))) pos += 1;
  };

  function parseString() {
    pos += 1; // opening quote
    let out = "";
    let start = pos;
    for (;;) {
      if (pos >= text.length) fail("unterminated string", start - 1);
      const code = text.charCodeAt(pos);
      if (code === 0x22) {
        out += text.slice(start, pos);
        pos += 1;
        return out;
      }
      if (code < 0x20) fail("unescaped control character in string");
      if (code === 0x5c) {
        out += text.slice(start, pos);
        const escape = text[pos + 1];
        if (escape === "u") {
          const hex = text.slice(pos + 2, pos + 6);
          if (!/^[0-9a-fA-F]{4}$/.test(hex)) fail("invalid \\u escape");
          out += String.fromCharCode(parseInt(hex, 16));
          pos += 6;
        } else if (escape !== undefined && Object.hasOwn(SIMPLE_ESCAPES, escape)) {
          out += SIMPLE_ESCAPES[escape];
          pos += 2;
        } else {
          fail("invalid escape");
        }
        start = pos;
      } else {
        pos += 1;
      }
    }
  }

  function parseValue() {
    skip();
    if (pos >= text.length) fail("unexpected end of input");
    const char = text[pos];
    if (char === "{") {
      pos += 1;
      const result = {};
      skip();
      if (text[pos] === "}") {
        pos += 1;
        return result;
      }
      for (;;) {
        skip();
        if (text[pos] !== '"') fail("expected a string key");
        const keyAt = pos;
        const key = parseString();
        if (Object.hasOwn(result, key) && duplicates !== "last") fail(`duplicate object key ${JSON.stringify(key)}`, keyAt);
        skip();
        if (text[pos] !== ":") fail("expected ':'");
        pos += 1;
        setOwn(result, key, parseValue());
        skip();
        if (text[pos] === ",") {
          pos += 1;
        } else if (text[pos] === "}") {
          pos += 1;
          return result;
        } else {
          fail("expected ',' or '}'");
        }
      }
    }
    if (char === "[") {
      pos += 1;
      const result = [];
      skip();
      if (text[pos] === "]") {
        pos += 1;
        return result;
      }
      for (;;) {
        result.push(parseValue());
        skip();
        if (text[pos] === ",") {
          pos += 1;
        } else if (text[pos] === "]") {
          pos += 1;
          return result;
        } else {
          fail("expected ',' or ']'");
        }
      }
    }
    if (char === '"') return parseString();
    for (const [literal, value] of [["true", true], ["false", false], ["null", null]]) {
      if (text.startsWith(literal, pos)) {
        pos += literal.length;
        return value;
      }
    }
    NUMBER_AT.lastIndex = pos;
    const match = NUMBER_AT.exec(text);
    if (match === null) fail(`unexpected character ${JSON.stringify(char)}`);
    pos += match[0].length;
    return number(match[0]);
  }

  const value = parseValue();
  skip();
  if (pos < text.length) fail("unexpected data after the first JSON value");
  return value;
}

const DECODER = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });

/** Decode UTF-8 strictly: invalid sequences throw, and a byte order mark is kept (and so fails JSON parsing). */
export function decodeUtf8(bytes) {
  return DECODER.decode(bytes);
}

/** Resolve an RFC 6901 JSON Pointer; throws RangeError when it does not lead to a value. */
export function resolvePointer(document, pointer) {
  if (pointer === "") return document;
  if (!pointer.startsWith("/")) throw new RangeError(`JSON Pointer ${JSON.stringify(pointer)} must be empty or start with "/"`);
  let node = document;
  for (const raw of pointer.slice(1).split("/")) {
    if (/~(?![01])/.test(raw)) throw new RangeError(`JSON Pointer ${JSON.stringify(pointer)} has an invalid escape`);
    const token = raw.replaceAll("~1", "/").replaceAll("~0", "~");
    if (Array.isArray(node)) {
      if (!/^(?:0|[1-9][0-9]*)$/.test(token) || Number(token) >= node.length) {
        throw new RangeError(`JSON Pointer ${JSON.stringify(pointer)}: no array element ${JSON.stringify(token)}`);
      }
      node = node[Number(token)];
    } else if (node !== null && typeof node === "object" && !(node instanceof RawNumber) && Object.hasOwn(node, token)) {
      node = node[token];
    } else {
      throw new RangeError(`JSON Pointer ${JSON.stringify(pointer)}: no member ${JSON.stringify(token)}`);
    }
  }
  return node;
}
