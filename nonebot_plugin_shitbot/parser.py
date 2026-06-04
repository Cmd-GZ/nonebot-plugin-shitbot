from typing import Any


class BotArgParser:
    def __init__(self):
        self._subparsers: dict[str, BotArgParser] = {}
        self._opts_rule: dict[str, dict[str, Any]] = {}
        self._opts_value: dict[str, list[Any]] = {}
        self._rule: dict[str, Any] = {}
        self._value: list[Any] = []
        self._subcmd: str | None = None
        self.err: str = ""
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
        choice: list[str] | None = None,
        type: type = str,
        max_appeared: int | None = 1,
        default: list[Any] | None = None,
    ):
        self._opts_rule[name] = {
            "required": required,
            "necessary": necessary,
            "choice": choice,
            "type": type,
            "max_appeared": max_appeared,
            "default": default if default is not None else [],
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

    def _can_convert(self, s: str, t: type) -> bool:
        try:
            t(s)
            return True
        except ValueError:
            return False

    def _partition(
        self, argv: list[str]
    ) -> tuple[list[list[str]], str | None, list[str]]:
        subparsers = self._subparsers.keys()
        own_argv = argv
        subcmd = None
        aub_argv = []
        for i in range(len(argv)):
            if argv[i] in subparsers:
                subcmd = argv[i]
                own_argv = argv[:i]
                aub_argv = argv[i + 1 :]
                break

        options = self._opts_rule.keys()
        options_count = dict.fromkeys(options, 0)
        partitioned = []

        prev = 0
        for i in range(len(own_argv)):
            if own_argv[i] in options:
                if (
                    self._opts_rule[own_argv[i]]["max_appeared"] is not None
                    and options_count[own_argv[i]]
                    >= self._opts_rule[own_argv[i]]["max_appeared"]
                ):
                    continue
                options_count[own_argv[i]] += 1
                partitioned.append(own_argv[prev:i])
                prev = i
        partitioned.append(own_argv[prev:])
        return (partitioned, subcmd, aub_argv)

    def _tidy_partitioned(self, partitioned: list[list[str]]) -> list[str] | None:
        # Separate partitioned into [option args parts] and the normal arguments part
        # partitioned should be the result[0] of self._partition
        # partitioned will store [option args parts]
        # the function will return the normal arguments part
        partitioned_last = partitioned.pop(-1)
        # the first case
        if len(partitioned) < 1:
            return partitioned_last

        # the second case
        if self._opts_rule[partitioned_last[0]]["required"]:
            partitioned.append(partitioned_last[0:2])
            partitioned_last.pop(0)
        else:
            partitioned.append(partitioned_last[0:1])
        try:
            partitioned_last.pop(0)
            return partitioned_last
        except IndexError:
            return None

    def is_valid(self, argv: list[str]) -> bool:
        partitioned, subcmd, aub_argv = self._partition(argv)
        partitioned_length = len(partitioned)
        if partitioned_length == 0:
            return False
        if partitioned_length >= 2 and len(partitioned[0]) != 0:
            self.err = "Invalid arguments: " + " ".join(partitioned[0])
            return False

        # there are 2 rest cases of partitioned: [[value ...]] and [[], [option, value ...], [option, value ...], ..., [option, value ...]]

        partitioned_last = self._tidy_partitioned(partitioned)
        if partitioned_last is None:
            self.err = "Invalid arguments: " + argv[-1]
            return False
        # Now partitioned is [[], [option, value ...], [option, value ...], ...] or []
        # partitioned_last is [value ...]

        # judge partitioned
        options = self._opts_rule.keys()
        necessary_options = [
            option for option, rule in self._opts_rule.items() if rule["necessary"]
        ]
        for sublist in partitioned:
            sub_len = len(sublist)
            # fully igealled case
            if sub_len > 2:
                self.err = "Invalid arguments: " + " ".join(sublist)
                return False
            # for partitioned[0], partitioned[i] is empty iff i = 0
            if sub_len == 0:
                continue
            option = sublist[0]
            # for non-exist option
            if option not in options:
                self.err = "Invalid arguments: " + " ".join(sublist)
                return False
            # for required
            if (self._opts_rule[sublist[0]]["required"] and sub_len == 1) or (
                not self._opts_rule[sublist[0]]["required"] and sub_len == 2
            ):
                self.err = "Invalid arguments: " + " ".join(sublist)
                return False
            # now sub_len == 2 iff sublist[0] requires an argument (required=True)
            # for type
            if sub_len == 2 and not self._can_convert(
                sublist[1], self._opts_rule[sublist[0]]["type"]
            ):
                self.err = "Invalid arguments: " + " ".join(sublist)
                return False
            # for choice
            if (
                sub_len == 2
                and self._opts_rule[sublist[0]]["choice"] is not None
                and sublist[1] not in self._opts_rule[sublist[0]]["choice"]
            ):
                self.err = "Invalid arguments: " + " ".join(sublist)
                return False
            # for necessary
            if sublist[0] in necessary_options:
                necessary_options.remove(sublist[0])

        # for necessary
        if necessary_options:
            self.err = f"options are necessary: {', '.join(necessary_options)}"
            return False

        # judge partitioned_last
        # for the number of normal arguments
        length_last = len(partitioned_last)
        if (length_last < self._rule["min"]) or (
            self._rule["max"] is not None and length_last > self._rule["max"]
        ):
            self.err = "Invalid arguments: " + " ".join(partitioned_last)
            return False
        # for the types
        length_types = len(self._rule["types"])
        for i in range(len(partitioned_last)):
            value = partitioned_last[i]
            if not self._can_convert(
                value, self._rule["types"][i if i < length_types else -1]
            ):
                self.err = "Invalid arguments: " + " ".join(partitioned_last)
                return False

        if subcmd is None and self._rule["need_subcmd"]:
            self.err = "subcommand is necessary"
            return False

        if subcmd is not None:
            if subcmd not in self._subparsers:
                return False
            if not self._subparsers[subcmd].is_valid(aub_argv):
                self.err = self._subparsers[subcmd].err
                return False

        return True

    def parse_argv(self, argv: list[str]):
        if not self.is_valid(argv):
            raise ValueError("Invalid arguments")

        self._opts_value = {}
        self._value = []
        self._subcmd = None

        partitioned, subcmd, aub_argv = self._partition(argv)
        options = self._opts_rule.keys()

        partitioned_last = self._tidy_partitioned(partitioned)
        if partitioned_last is None:
            raise ValueError("Invalid arguments")

        for sublist in partitioned:
            if len(sublist) == 0:
                continue
            option = sublist[0]
            opt_values = self._opts_value.get(option)
            if opt_values is None:
                opt_values = []
            if self._opts_rule[option]["required"]:
                value = sublist[1]
                value = self._opts_rule[option]["type"](value)
                opt_values.append(value)
            else:
                if len(opt_values) == 0:
                    opt_values = [0]
                value = opt_values.pop()
                value += 1
                opt_values.append(value)
            self._opts_value[option] = opt_values

        for i in range(len(partitioned_last)):
            index = i if i < len(self._rule["types"]) else len(self._rule["types"]) - 1
            value = partitioned_last[i]
            value = self._rule["types"][index](value)
            self._value.append(value)

        for option in options:
            if self._opts_value.get(option) is None:
                self._opts_value[option] = self._opts_rule[option]["default"]

        if subcmd is not None:
            self._subcmd = subcmd
            self._subparsers[subcmd].parse_argv(aub_argv)
