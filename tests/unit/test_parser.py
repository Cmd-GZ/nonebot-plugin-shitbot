"""Unit tests for BotArgParser — no NoneBot initialization needed."""

import pytest
from nonebot_plugin_shitbot.parser import BotArgParser


class TestOptRequired:
    def test_required_opt_missing_value_invalid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True)
        assert not parser.is_valid(["-a"])

    def test_not_required_opt_with_value_invalid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=False)
        parser.add_opt("-b", required=False)
        assert not parser.is_valid(["-a", "1", "-b"])

    def test_not_required_opt_missing_value_valid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=False)
        assert parser.is_valid(["-a"])

    def test_required_take_next_arg_as_value(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True)
        parser.add_opt("-b", required=True)
        parser.parse_argv(["-a", "1", "-b", "2"])
        assert parser.opts_value["-a"] == ["1"]
        assert parser.opts_value["-b"] == ["2"]

    def test_required_take_only_one_arg_per_opt(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True)
        parser.parse_argv(["-a", "1", "2"])
        assert parser.opts_value["-a"] == ["1"]

    def test_required_multi_same_opt_values(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True, max_appeared=None)
        parser.parse_argv(["-a", "1", "-a", "2"])
        assert parser.opts_value["-a"] == ["1", "2"]
        parser.parse_argv(["-a", "1", "-a", "2", "-a", "3"])
        assert parser.opts_value["-a"] == ["1", "2", "3"]

    def test_not_required_take_zero_arg(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=False)
        parser.parse_argv(["-a", "btw"])
        assert parser.opts_value["-a"] != ["btw"]

    def test_not_required_values_equal_to_appeared_times(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=False, max_appeared=None)
        parser.parse_argv(["-a"])
        assert parser.opts_value["-a"] == [1]
        parser.parse_argv(["-a", "-a"])
        assert parser.opts_value["-a"] == [2]
        parser.parse_argv(["-a", "-a", "-a"])
        assert parser.opts_value["-a"] == [3]


class TestOptNecessary:
    def test_necessary_opt_missed_invalid(self):
        parser = BotArgParser()
        parser.add_opt("-a", necessary=True)
        assert not parser.is_valid([])
        parser.add_opt("-b", necessary=True)
        assert not parser.is_valid(["-a"])
        assert not parser.is_valid(["-b"])

    def test_necessary_opt_appeared_valid(self):
        parser = BotArgParser()
        parser.add_opt("-a", necessary=True)
        assert parser.is_valid(["-a"])


class TestOptChoice:
    def test_value_not_in_choice_invalid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True, choice=["1", "2"])
        assert not parser.is_valid(["-a", "3"])

    def test_value_in_choice_valid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True, choice=["1", "2"])
        assert parser.is_valid(["-a", "1"])
        assert parser.is_valid(["-a", "2"])


class TestOptRequiredAndChoice:
    def test_not_required_with_not_none_choice_is_valid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=False, choice=["u", "v"])
        assert parser.is_valid(["-a"])


class TestOptType:
    def test_failed_converted_value_invalid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True, type=int)
        parser.add_opt("-b", required=True, type=float)
        assert not parser.is_valid(["-a", "a"])
        assert not parser.is_valid(["-a", "1.1"])
        assert not parser.is_valid(["-b", "a"])

    def test_successfully_converted_value_valid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True, type=int)
        parser.add_opt("-b", required=True, type=float)
        assert parser.is_valid(["-a", "1"])
        assert parser.is_valid(["-a", "-1"])
        assert parser.is_valid(["-b", "1"])
        assert parser.is_valid(["-b", "-1"])
        assert parser.is_valid(["-b", "1.1"])

    def test_if_parser_will_convert_the_value(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True, type=int)
        parser.add_opt("-b", required=True, type=float)
        parser.parse_argv(["-a", "-1", "-b", "1.1"])
        assert parser.opts_value["-a"] == [-1]
        assert parser.opts_value["-b"] == [1.1]


class TestOptMax:
    def test_opts_identified_times_is_not_greater_than_max_appeared(self):
        parser = BotArgParser()
        parser.add_opt("-a", max_appeared=2)
        parser.parse_argv(["-a", "-a", "-a"])
        assert parser.opts_value["-a"] == [2]

    def test_opts_with_none_max_appeared_will_be_identified_any_times(self):
        parser = BotArgParser()
        parser.add_opt("-a", max_appeared=None)
        parser.parse_argv(["-a"] * 114514)
        assert parser.opts_value["-a"] == [114514]


class TestOptDefault:
    def test_opts_with_default_values(self):
        parser = BotArgParser()
        parser.add_opt("-a", default=["1", "2"])
        parser.parse_argv([])
        assert parser.opts_value["-a"] == ["1", "2"]


class TestValsRange:
    def test_values_out_of_range_invalid(self):
        parser = BotArgParser()
        parser.set_rule(min=1, max=2)
        assert not parser.is_valid([])
        assert not parser.is_valid(["1", "2", "3"])

    def test_values_max_equals_none_iff_infinity_length(self):
        parser = BotArgParser()
        parser.set_rule(min=1, max=None)
        parser.parse_argv(["a"] * 114514)
        assert len(parser.value) == 114514


class TestValsTypes:
    def test_values_failed_converted_value_invalid(self):
        parser = BotArgParser()
        parser.set_rule(types=[int])
        assert not parser.is_valid(["1", "2", "1.1"])
        parser.set_rule(types=[str, int, float, int])
        assert not parser.is_valid(["a", "-2", "1.1", "2.33"])
        assert not parser.is_valid(["1", "-2", "3.14", "2", "114.514"])

    def test_values_if_return_correct_type_values(self):
        parser = BotArgParser()
        parser.set_rule(types=[int])
        parser.parse_argv(["1", "2", "3"])
        assert all(isinstance(i, int) for i in parser.value)
        parser.set_rule(types=[str, int, float, int])
        parser.parse_argv(["1", "2", "3", "4", "5", "6", "7"])
        assert isinstance(parser.value[0], str)
        assert isinstance(parser.value[1], int)
        assert isinstance(parser.value[2], float)
        assert all(isinstance(i, int) for i in parser.value[3:])


class TestValsNeedSubcmd:
    def test_if_parser_with_need_subcmd_and_no_subcmd_is_invalid(self):
        parser = BotArgParser()
        parser.add_subparser("a")
        parser.set_rule(need_subcmd=True)
        assert not parser.is_valid(["1", "2", "3"])


class TestOptValsComb:
    def test_if_opt_will_be_parsed_as_a_normal_value_after_appeared_max_appeared_times(
        self,
    ):
        parser = BotArgParser()
        parser.add_opt("-a", max_appeared=2)
        parser.parse_argv(["-a", "-a", "-a", "-a"])
        assert parser.value == ["-a", "-a"]

    def test_case_opt_val_val_if_the_last_val_is_in_value(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True)
        parser.parse_argv(["-a", "1", "2"])
        assert parser.value == ["2"]


class TestOthers:
    def test_if_case_opt_val_val_opt_invalid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True)
        parser.add_opt("-b", required=True)
        assert not parser.is_valid(["-a", "1", "2", "-b", "3"])

    def test_if_case_val_opt_invalid(self):
        parser = BotArgParser()
        parser.add_opt("-a", required=True)
        parser.add_opt("-b", required=True)
        assert not parser.is_valid(["1", "-a", "2", "-b", "3"])


class TestSubcmd:
    def test_invalid_if_subcmd_is_invalid(self):
        parser = BotArgParser()
        parser.add_subparser("a")
        a = parser.subparsers["a"]
        a.set_rule(max=0)
        assert not parser.is_valid(["a", "1"])

    def test_valid_if_ownpart_and_subcmd_are_valid(self):
        parser = BotArgParser()
        parser.add_subparser("a")
        parser.set_rule(min=1, max=1)
        a = parser.subparsers["a"]
        a.set_rule(min=1, max=1)
        assert parser.is_valid(["1", "a", "1"])

    def test_if_parent_and_subcmd_not_shared_opts(self):
        parser = BotArgParser()
        parser.add_subparser("a")
        parser.add_opt("-v")
        a = parser.subparsers["a"]
        a.add_opt("-u")
        parser.parse_argv(["-u", "a", "-v"])
        assert parser.value == ["-u"]
        assert a.value == ["-v"]
        assert parser.opts_value.get("-u") is None
        assert a.opts_value.get("-v") is None

    def test_if_parent_and_subcmd_not_shared_opt_values(self):
        parser = BotArgParser()
        parser.add_subparser("a")
        parser.add_opt("-v", required=True)
        a = parser.subparsers["a"]
        a.add_opt("-v", required=True)
        parser.parse_argv(["-v", "1", "a", "-v", "2"])
        assert parser.opts_value["-v"] == ["1"]
        assert a.opts_value["-v"] == ["2"]

    def test_if_parent_and_subcmd_not_shared_values(self):
        parser = BotArgParser()
        parser.add_subparser("a")
        a = parser.subparsers["a"]
        parser.parse_argv(["1", "2", "a", "3", "4"])
        assert parser.value == ["1", "2"]
        assert a.value == ["3", "4"]

    def test_if_subcmds_not_shared_opts(self):
        parser = BotArgParser()
        parser.add_subparser("a")
        parser.add_subparser("b")
        a = parser.subparsers["a"]
        b = parser.subparsers["b"]
        a.add_opt("-v")
        b.add_opt("-u")
        parser.parse_argv(["a", "-u"])
        assert a.value == ["-u"]
        assert a.opts_value.get("-u") is None
        parser.parse_argv(["b", "-v"])
        assert b.value == ["-v"]
        assert b.opts_value.get("-v") is None

    def test_if_register_same_subcmd_more_than_once_then_will_share_the_same_subparser(
        self,
    ):
        parser = BotArgParser()
        parser.add_subparser("a")
        a = parser.subparsers["a"]
        a.add_opt("-v")
        parser.add_subparser("a")
        a.add_opt("-u")
        parser.parse_argv(["a", "-u", "-v"])
        assert a.opts_value["-u"] == [1]
        assert a.opts_value["-v"] == [1]

    def test_if_parse_argv_raise_when_give_it_an_invalid_argv(self):
        parser = BotArgParser()
        parser.add_opt("-v", required=True)
        with pytest.raises(ValueError):
            parser.parse_argv(["-v"])