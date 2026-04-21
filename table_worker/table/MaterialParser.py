from lark import Lark, Transformer


grammar = '''
start: material

material: spd_base
        | spd_with_suffix

spd_base: prefix NUMBER "мм"? "(" layers ")"
spd_with_suffix: prefix NUMBER "мм"? "(" layers ")" suffix

layers: NUMBER (("–" | "-" | "+") NUMBER)*

prefix: /[А-Я]+/
NUMBER: /\\d+/
suffix: /[А-Я]+/

%import common.WS
%ignore WS
'''


class SpdTransformer(Transformer):
    def prefix(self, items):
        return str(items[0])

    def suffix(self, items):
        return str(items[0])

    def NUMBER(self, n):
        return int(n)

    def layers(self, items):
        return list(items)

    def spd_base(self, items):
        prefix, total_thickness, layers = items
        return {
            "prefix": prefix,
            "total": total_thickness,
            "layers": layers
        }

    def spd_with_suffix(self, items):
        prefix, total_thickness, layers, suffix = items
        return {
            "prefix": prefix,
            "total": total_thickness,
            "layers": layers,
            "suffix": suffix
        }

    def material(self, items):
        return items[0]


parser = Lark(grammar, start='material', parser='lalr')
transformer = SpdTransformer()

test_strings = [
    "СПД 32мм (4-10-4-10-4)",
    "СПД 40мм (4-14-4-14-4)",
    "СПД 40мм (4-14-4-14-4) НФ",
    "СП24 (4-16-4)",
    "СПД40 (4М1-14Ar-4М1-14Ar-И4зак)"
]

for text in test_strings:
    try:
        tree = parser.parse(text)
        result = transformer.transform(tree)
        print(result)
    except Exception:
        print("Wrong format:", text)

