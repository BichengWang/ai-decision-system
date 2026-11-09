import assert from "node:assert/strict";
import { test } from "node:test";
import { JsonSyntaxError, RawNumber, parseJson, rawNumber, resolvePointer } from "../checks/json.mjs";

test("parses RFC 8259 values", () => {
  assert.deepEqual(parseJson(' {"a": [1, 2.5, -0, 1e3, "x\\u00e9\\n", true, false, null], "b": {}} '), {
    a: [1, 2.5, -0, 1000, "x\u00e9\n", true, false, null],
    b: {},
  });
});

test("rejects malformed JSON", () => {
  for (const text of ["", "{", "[1,]", '{"a":1,}', "01", "+1", "1.", ".5", "NaN", "Infinity", "'a'", '"\u0001"',
    '"\\x"', '"\\u12G4"', "[1] 2", "\uFEFF{}", '{"a" 1}', "tru"]) {
    assert.throws(() => parseJson(text), JsonSyntaxError, JSON.stringify(text));
  }
});

test("rejects duplicate object keys at any depth", () => {
  assert.throws(() => parseJson('{"a":1,"a":2}'), /duplicate object key "a"/);
  assert.throws(() => parseJson('[{"x":{"k":1,"k\\u0000":2,"\\u006b":3}}]'), /duplicate object key "k"/);
});

test("duplicates: last keeps the last value in the first position, as JSON.parse does", () => {
  const text = '{"a":1,"b":2,"a":{"c":3,"c":4}}';
  const value = parseJson(text, { duplicates: "last" });
  assert.deepEqual(value, JSON.parse(text));
  assert.deepEqual(Object.keys(value), Object.keys(JSON.parse(text)));
});

test("keeps __proto__ as an ordinary member", () => {
  const value = parseJson('{"__proto__":{"polluted":true}}');
  assert.equal(Object.getPrototypeOf(value), Object.prototype);
  assert.deepEqual(Object.keys(value), ["__proto__"]);
  assert.equal({}.polluted, undefined);
});

test("integer literals beyond 2^53-1 become BigInt, floats stay numbers", () => {
  assert.equal(parseJson("9007199254740991"), 9007199254740991);
  assert.equal(parseJson("9007199254740992"), 9007199254740992n);
  assert.equal(parseJson("-123456789012345678901234"), -123456789012345678901234n);
  assert.equal(parseJson("1e30"), 1e30);
  assert.equal(parseJson("1000000000000000000000.0"), 1e21);
});

test("raw number mode keeps the literal", () => {
  const value = parseJson("[1.0, 1e-07, -0, 12345678901234567890]", { number: rawNumber });
  assert.deepEqual(value.map((item) => item.text), ["1.0", "1e-07", "-0", "12345678901234567890"]);
  assert.ok(value[0] instanceof RawNumber);
});

test("resolves RFC 6901 pointers", () => {
  const document = parseJson('{"":1,"a/b":2,"m~n":3,"list":[{"k":"v"},4],"x":{"y":null}}');
  assert.equal(resolvePointer(document, ""), document);
  assert.equal(resolvePointer(document, "/"), 1);
  assert.equal(resolvePointer(document, "/a~1b"), 2);
  assert.equal(resolvePointer(document, "/m~0n"), 3);
  assert.equal(resolvePointer(document, "/list/0/k"), "v");
  assert.equal(resolvePointer(document, "/x/y"), null);
  for (const pointer of ["a", "/missing", "/list/2", "/list/01", "/list/-", "/a~2", "/x/y/z"]) {
    assert.throws(() => resolvePointer(document, pointer), RangeError, pointer);
  }
});
