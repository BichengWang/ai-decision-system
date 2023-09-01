import re

text = """
 1112  2023-09-01 04:53  git push --force origin nv_dev
 1113  2023-09-01 04:54  git log
 1114  2023-09-01 04:54  ./tools/ubuild.sh --branch nv_dev --artifact ml-code-nv-pricing --region phx\n
 1115  2023-09-01 04:56  history
 1116  2023-09-01 04:56  history -l 1000
 1117  2023-09-01 04:56  history -i 1000
"""

output_format = "git push --delete origin {}"


def main():
    pattern = r'git br -D (\w+)'
    matches = re.findall(pattern, text)
    for match in matches:
        print(output_format.format(match))
    return


if __name__ == "__main__":
    main()