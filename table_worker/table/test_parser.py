import re


text_obj = "СПД52: 8LPSESILVER60З(Ф)-16WP9005-6М1(Ф)-16WP9005-6И(Ф)(ПС)[ПР]"

sep = "\s*"
mat = "СП[ДО]?"
size = f"\(?\d*\)?{sep}(мм)?"
stuff = "[\(:]?"
pattern = rf"^({mat}{sep}{size}{sep}){sep}{stuff}{sep}(.*)$"

prefix_pattern = re.compile(pattern, re.IGNORECASE)

match = prefix_pattern.match(text_obj)

if match:
    print(match.groups())
else:
    print("err")

