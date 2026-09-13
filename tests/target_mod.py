def plain(a, b=0):
    return a + b

class Calc:
    def add(self, x):
        return x + 1

calls = []

def record_len():
    calls.append(1)
    return len(calls)
