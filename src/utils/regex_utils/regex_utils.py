import re


def find_indices(content, reg):
    return [m.start(0) for m in re.finditer(reg, content)]


def find_content(content, reg):
    return re.findall(reg, content)


if __name__ == "__main__":
    content = 'an example word:cat and word:dog'
    reg = r'word:\w'
    print(find_indices(content, reg))
    print(find_content(content, reg))
