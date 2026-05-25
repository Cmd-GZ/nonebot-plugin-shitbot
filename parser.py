from typing import Any

class BotArgParser:
    def __init__(self):
        self._subparsers: dict[str, BotArgParser] = {}
        self._args_rule: dict[str, dict[str, Any]] = {}
        self._args_value: dict[str, Any] = {}
        self._rule: dict[str, Any] = {}
        self._value: list[Any] = []

    @property
    def subparsers(self):
        return self._subparsers

    @property
    def args_value(self):
        return self._args_value

    @property
    def value(self):
        return self._value

    def add_subparser(self, name: str):
        if name in self._subparsers:
            return self._subparsers[name]
        self._subparsers[name] = BotArgParser()
        return self._subparsers[name]

    def add_argument(
        self, name: str,
        *,
        required: bool = False,
        necessary: bool = False,
        choice: list[Any] | None = None,
        type: type = str,
        max_appeared: int = 1,
        default: Any = None
    ):
        self._args_rule[name] = {
            'required': required,
            'necessary': necessary,
            'choice': choice,
            'type': type,
            'max_appeared': max_appeared,
            'default': default
        }

    def set_rule(self, *, min: int = 0, max: int | None = None, types: list[type] = [str]):
        self._rule = {
            'min': min,
            'max': max,
            'types': types,
        }

    def _is_int(self, s: str) -> bool:
        try:
            int(s)
            return True
        except ValueError:
            return False

    def _partition(self, args: list[str]) -> tuple[list[list[str]], str | None, list[str]]:
        subparsers = self._subparsers.keys()
        ownargs = args
        subcmd = None
        subargs = []
        for i in range(len(args)):
            if args[i] in subparsers:
                subcmd = args[i]
                ownargs = args[:i]
                subargs = args[i+1:]
                break

        options = self._args_rule.keys()
        options_count = {option: 0 for option in options}
        partitioned = []

        prev = 0
        for i in range(len(ownargs)):
            if ownargs[i] in options:
                if options_count[ownargs[i]] >= self._args_rule[ownargs[i]]['max_appeared']:
                    continue
                options_count[ownargs[i]] += 1
                partitioned.append(ownargs[prev:i])
                prev = i
        partitioned.append(ownargs[prev:])
        return (partitioned, subcmd, subargs)

    def is_valid(self, args: list[str]) -> bool:
        partitioned, subcmd, subargs = self._partition(args)
        lenp = len(partitioned)
        if lenp == 0: return False
        if lenp >= 2 and partitioned[0] != []:
            return False

        options = self._args_rule.keys()
        necessary_options = [option for option, rule in self._args_rule.items() if rule['necessary']]
        for sublist in partitioned[:-1]:
            l = len(sublist)
            if l >= 3: return False
            if l == 0: continue
            if sublist[0] not in options: return False
            if self._args_rule[sublist[0]]['required'] and l == 1: return False
            if not self._args_rule[sublist[0]]['required'] and l == 2: return False
            if l == 2 and self._args_rule[sublist[0]]['type'] == int and not self._is_int(sublist[1]):
                return False
            if l == 2 and self._args_rule[sublist[0]]['choice'] is not None and sublist[1] not in self._args_rule[sublist[0]]['choice']:
                return False
            if sublist[0] in necessary_options:
                necessary_options.remove(sublist[0])

        partitioned_last = partitioned[-1]
        if lenp >= 2:
            if partitioned_last[0] not in options: return False
            if self._args_rule[partitioned_last[0]]['required'] and len(partitioned_last) == 1: return False
            if self._args_rule[partitioned_last[0]]['required'] and self._args_rule[partitioned_last[0]]['type'] == int and not self._is_int(partitioned_last[1]):
                return False
            if self._args_rule[partitioned_last[0]]['required'] and self._args_rule[partitioned_last[0]]['choice'] is not None and partitioned_last[1] not in self._args_rule[partitioned_last[0]]['choice']:
                return False
            if partitioned_last[0] in necessary_options: necessary_options.remove(partitioned_last[0])
            if self._args_rule[partitioned_last[0]]['required']: partitioned_last = partitioned_last[2:]
            else: partitioned_last = partitioned_last[1:]

        partitioned_last_len = len(partitioned_last)
        if partitioned_last_len < self._rule['min']: return False
        if self._rule['max'] is not None and partitioned_last_len > self._rule['max']: return False
        for i in range(partitioned_last_len):
            if self._rule['types'] is None: break
            index = i if i < len(self._rule['types']) else len(self._rule['types']) - 1
            if self._rule['types'][index] == int and not self._is_int(partitioned_last[i]):
                return False

        if necessary_options:
            return False

        if subcmd is not None:
            if subcmd not in self._subparsers: return False
            if not self._subparsers[subcmd].is_valid(subargs): return False

        return True

    def parse_args(self, args: list[str]):
        if not self.is_valid(args):
            raise ValueError("Invalid arguments")

        partitioned, subcmd, subargs = self._partition(args)
        options = self._args_rule.keys()
        for option in options:
            self._args_value[option] = self._args_rule[option]['default']

        partitioned_last = partitioned.pop(-1)
        if len(partitioned) >= 1:
            if self._args_rule[partitioned_last[0]]['required']:
                partitioned.append(partitioned_last[0:2])
                partitioned_last.pop(0)
            else:
                partitioned.append(partitioned_last[0:1])
            partitioned_last.pop(0)

        for sublist in partitioned:
            if len(sublist) == 0: continue
            option = sublist[0]
            if self._args_rule[option]['required']:
                value = sublist[1]
                if self._args_rule[option]['type'] == int:
                    value = int(value)
                if self._args_value[option] is None: self._args_value[option] = []
                self._args_value[option].append(value)

        for i in range(len(partitioned_last)):
            index = i if i < len(self._rule['types']) else len(self._rule['types']) - 1
            value = partitioned_last[i]
            if self._rule['types'][index] == int:
                value = int(value)
            self._value.append(value)

        if subcmd is not None:
            self._subparsers[subcmd].parse_args(subargs)

