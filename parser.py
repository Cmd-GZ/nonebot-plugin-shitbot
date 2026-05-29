from typing import Any


class BotArgParser:
    def __init__(self):
        self._subparsers: dict[str, BotArgParser] = {}
        self._opts_rule: dict[str, dict[str, Any]] = {}
        self._opts_value: dict[str, list[Any] | None] = {}
        self._rule: dict[str, Any] = {}
        self._value: list[Any] = []
        self._subcmd: str | None = None
        self.set_rule()

    @property
    def subparsers(self):
        return self._subparsers

    @property
    def subcmd(self):
        return self._subcmd

    @property
    def subparser(self):
        if self._subcmd is None:
            return None
        return self._subparsers[self._subcmd]

    @property
    def opts_value(self):
        return self._opts_value

    @property
    def value(self):
        return self._value

    def add_subparser(self, name: str):
        if name in self._subparsers:
            return self._subparsers[name]
        self._subparsers[name] = BotArgParser()
        return self._subparsers[name]

    def add_opt(
        self,
        name: str,
        *,
        required: bool = False,
        necessary: bool = False,
        choice: list[Any] | None = None,
        type: type = str,
        max_appeared: int = 1,
        default: list[Any] | None = None,
    ):
        self._opts_rule[name] = {
            "required": required,
            "necessary": necessary,
            "choice": choice,
            "type": type,
            "max_appeared": max_appeared,
            "default": default,
        }

    def set_rule(
        self,
        *,
        min: int = 0,
        max: int | None = None,
        types: list[type] = [str],
        need_subcmd: bool = False,
    ):
        self._rule = {
            "min": min,
            "max": max,
            "types": types,
            "need_subcmd": need_subcmd,
        }

    def _is_int(self, s: str) -> bool:
        try:
            int(s)
            return True
        except ValueError:
            return False

    def _is_float(self, s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _partition(
        self, argv: list[str]
    ) -> tuple[list[list[str]], str | None, list[str]]:
        subparsers = self._subparsers.keys()
        ownargv = argv
        subcmd = None
        subargv = []
        for i in range(len(argv)):
            if argv[i] in subparsers:
                subcmd = argv[i]
                ownargv = argv[:i]
                subargv = argv[i + 1:]
                break

        options = self._opts_rule.keys()
        options_count = dict.fromkeys(options, 0)
        partitioned = []

        prev = 0
        for i in range(len(ownargv)):
            if ownargv[i] in options:
                if (
                    options_count[ownargv[i]]
                    >= self._opts_rule[ownargv[i]]["max_appeared"]
                ):
                    continue
                options_count[ownargv[i]] += 1
                partitioned.append(ownargv[prev:i])
                prev = i
        partitioned.append(ownargv[prev:])
        return (partitioned, subcmd, subargv)

    def is_valid(self, argv: list[str]) -> bool:
        partitioned, subcmd, subargv = self._partition(argv)
        lenp = len(partitioned)
        if lenp == 0:
            return False
        if lenp >= 2 and partitioned[0] != []:
            return False

        options = self._opts_rule.keys()
        necessary_options = [
            option for option, rule in self._opts_rule.items() if rule["necessary"]
        ]
        for sublist in partitioned[:-1]:
            sub_len = len(sublist)
            if sub_len >= 3:
                return False
            if sub_len == 0:
                continue
            if sublist[0] not in options:
                return False
            if self._opts_rule[sublist[0]]["required"] and sub_len == 1:
                return False
            if not self._opts_rule[sublist[0]]["required"] and sub_len == 2:
                return False
            if (
                sub_len == 2
                and self._opts_rule[sublist[0]]["type"] == int
                and not self._is_int(sublist[1])
            ):
                return False
            if (
                sub_len == 2
                and self._opts_rule[sublist[0]]["type"] == float
                and not self._is_float(sublist[1])
            ):
                return False
            if (
                sub_len == 2
                and self._opts_rule[sublist[0]]["choice"] is not None
                and sublist[1] not in self._opts_rule[sublist[0]]["choice"]
            ):
                return False
            if sublist[0] in necessary_options:
                necessary_options.remove(sublist[0])

        partitioned_last = partitioned[-1]
        if lenp >= 2:
            if partitioned_last[0] not in options:
                return False
            if (
                self._opts_rule[partitioned_last[0]]["required"]
                and len(partitioned_last) == 1
            ):
                return False
            if (
                self._opts_rule[partitioned_last[0]]["required"]
                and self._opts_rule[partitioned_last[0]]["type"] == int
                and not self._is_int(partitioned_last[1])
            ):
                return False
            if (
                self._opts_rule[partitioned_last[0]]["required"]
                and self._opts_rule[partitioned_last[0]]["type"] == float
                and not self._is_float(partitioned_last[1])
            ):
                return False
            if (
                self._opts_rule[partitioned_last[0]]["required"]
                and self._opts_rule[partitioned_last[0]]["choice"] is not None
                and partitioned_last[1]
                not in self._opts_rule[partitioned_last[0]]["choice"]
            ):
                return False
            if partitioned_last[0] in necessary_options:
                necessary_options.remove(partitioned_last[0])
            if self._opts_rule[partitioned_last[0]]["required"]:
                partitioned_last = partitioned_last[2:]
            else:
                partitioned_last = partitioned_last[1:]

        partitioned_last_len = len(partitioned_last)
        if partitioned_last_len < self._rule["min"]:
            return False
        if self._rule["max"] is not None and partitioned_last_len > self._rule["max"]:
            return False
        for i in range(partitioned_last_len):
            if self._rule["types"] is None:
                break
            index = i if i < len(self._rule["types"]) else len(self._rule["types"]) - 1
            if self._rule["types"][index] == int and not self._is_int(
                partitioned_last[i]
            ):
                return False
            if self._rule["types"][index] == float and not self._is_float(
                partitioned_last[i]
            ):
                return False

        if necessary_options:
            return False

        if subcmd is None and self._rule["need_subcmd"]:
            return False

        if subcmd is not None:
            if subcmd not in self._subparsers:
                return False
            if not self._subparsers[subcmd].is_valid(subargv):
                return False

        return True

    def parse_argv(self, argv: list[str]):
        if not self.is_valid(argv):
            raise ValueError("Invalid arguments")

        self._opts_value = {}
        self._value = []
        self._subcmd = None

        partitioned, subcmd, subargv = self._partition(argv)
        options = self._opts_rule.keys()

        partitioned_last = partitioned.pop(-1)
        if len(partitioned) >= 1:
            if self._opts_rule[partitioned_last[0]]["required"]:
                partitioned.append(partitioned_last[0:2])
                partitioned_last.pop(0)
            else:
                partitioned.append(partitioned_last[0:1])
            partitioned_last.pop(0)

        for sublist in partitioned:
            if len(sublist) == 0:
                continue
            option = sublist[0]
            if self._opts_rule[option]["required"]:
                value = sublist[1]
                if self._opts_rule[option]["type"] == int:
                    value = int(value)
                if self._opts_rule[option]["type"] == float:
                    value = float(value)
            else:
                value = True
            opt_values = self._opts_value.get(option)
            if opt_values is None:
                opt_values = []
                self._opts_value[option] = opt_values
            opt_values.append(value)

        for i in range(len(partitioned_last)):
            index = i if i < len(self._rule["types"]) else len(self._rule["types"]) - 1
            value = partitioned_last[i]
            if self._rule["types"][index] == int:
                value = int(value)
            if self._rule["types"][index] == float:
                value = float(value)
            self._value.append(value)

        for option in options:
            if self._opts_value.get(option) is None:
                self._opts_value[option] = self._opts_rule[option]["default"]

        if subcmd is not None:
            self._subcmd = subcmd
            self._subparsers[subcmd].parse_argv(subargv)
