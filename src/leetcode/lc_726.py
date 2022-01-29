class NumberOfAtoms:
    def countOfAtoms(self, formula: str) -> str:
        formula = "({})".format(formula)
        def multiple(d, num):
            if num < 2:
                return
            for k in d.keys():
                d[k] *= num
            return

        def fold_atoms(dic, n_crr, c_crr):
            n_crr = 1 if n_crr == 0 else n_crr
            if c_crr == '':
                return
            else:
                dic[c_crr] = dic.get(c_crr, 0) + n_crr

        def merge_dict(dic, dic2):
            for k in dic2.keys():
                dic[k] = dic.get(k, 0) + dic2[k]
        c_dict = dict()
        n_carry = 1
        c_carry = ''
        c_stack = []
        N = len(formula)
        i = 0
        while i < N:
            if formula[i].isdigit():
                n_carry = n_carry * 10 + int(formula[i])
                i += 1
            elif formula[i] == '(':
                fold_atoms(c_dict, n_carry, c_carry)
                c_carry, n_carry = '', 0
                c_stack.append(c_dict)
                c_dict = dict()
                i += 1
            elif formula[i] == ')':
                fold_atoms(c_dict, n_carry, c_carry)
                c_carry, n_carry = '', 0
                i += 1
                while i < N and formula[i].isdigit():
                    n_carry = n_carry * 10 + int(formula[i])
                    i += 1
                multiple(c_dict, n_carry)
                if c_stack:
                    merge_dict(c_dict, c_stack.pop())
            elif formula[i] >= 'A' and formula[i] <= 'Z':
                fold_atoms(c_dict, n_carry, c_carry)
                c_carry, n_carry = formula[i], 0
                i += 1
            else:
                c_carry += formula[i]
                i += 1

        def build_ret(dic):
            idx_list = sorted(dic.keys())
            ret = ""
            for idx in idx_list:
                ret += str(idx) + (str(dic[idx]) if dic[idx] > 1 else "")
            return ret

        return build_ret(c_dict)


if __name__ == "__main__":
    obj = NumberOfAtoms()
    print(obj.countOfAtoms("Be32"))
