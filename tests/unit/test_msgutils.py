"""
Unit tests for the pure logical part of msgutils
"""



from nonebot_plugin_shitbot.msgutils import (
    DumpedSeg,
    get_multimedias_url,
    msg_filter,
    msg_foldl,
    msg_foldr,
    msg_map,
)

inner_content = [
    {"type": "text", "data": {"text": "1"}},
    {
        "type": "image",
        "data": {"url": "https://github.com/Cmd-GZ/nonebot-plugin-shitbot"},
    },
    {"type": "text", "data": {"text": "2"}},
    {"type": "image", "data": {"url": "https://manyacg.top/setu"}},
]
inner_node = {
    "type": "node",
    "data": {"user_id": 1, "nickname": "inner", "content": inner_content},
}
node = {
    "type": "node",
    "data": {"user_id": 1, "nickname": "node", "content": [inner_node, inner_node]},
}
forward = {"type": "forward", "data": {"id": 1, "content": [inner_node, node]}}
msg = [forward]


class TestMsgFold:
    def test_msg_foldl(self):
        def _fold(acc: str, seg: DumpedSeg) -> str:
            if seg["type"] not in ["text", "node"]:
                return acc
            if seg["type"] == "text":
                return acc + seg["data"]["text"]
            return acc + seg["data"]["nickname"]

        assert msg_foldl(_fold, "", inner_content) == "12"
        assert msg_foldl(_fold, "", msg) == "inner12nodeinner12inner12"

    def test_msg_foldr(self):
        def _fold(seg: DumpedSeg, acc: str) -> str:
            if seg["type"] not in ["text", "node"]:
                return acc
            if seg["type"] == "text":
                return acc + seg["data"]["text"]
            return acc + seg["data"]["nickname"]

        assert msg_foldr(_fold, "", inner_content) == "21"
        assert msg_foldr(_fold, "", msg) == "21inner21innernode21inner"


class TestMsgMap:
    def test_msg_map(self):
        def _map(seg: DumpedSeg) -> DumpedSeg:
            if seg["type"] == "text":
                seg["data"]["text"] = "1"
            return seg

        def _fold(acc: int, seg: DumpedSeg) -> int:
            if seg["type"] != "text":
                return acc
            return acc + int(seg["data"]["text"])

        mapped_msg = msg_map(_map, msg)
        mapped_inner_content = msg_map(_map, inner_content)
        assert msg_foldl(_fold, 0, msg) == 9
        assert msg_foldl(_fold, 0, inner_content) == 3
        assert msg_foldl(_fold, 0, mapped_msg) == 6
        assert msg_foldl(_fold, 0, mapped_inner_content) == 2


class TestMsgFilter:
    def test_msg_filter(self):
        def _filter(seg: DumpedSeg) -> bool:
            return seg["type"] != "text"

        filtered_msg = msg_filter(_filter, msg)
        filtered_inner_content = msg_filter(_filter, inner_content)

        def _fold(acc: int, seg: DumpedSeg) -> int:
            if seg["type"] != "text":
                return acc
            return acc + int(seg["data"]["text"])

        assert msg_foldl(_fold, 0, msg) == 9
        assert msg_foldl(_fold, 0, inner_content) == 3
        assert msg_foldl(_fold, 0, filtered_msg) == 0
        assert msg_foldl(_fold, 0, filtered_inner_content) == 0


class TestMsgGetUrls:
    def test_get_urls(self):
        assert (
            get_multimedias_url(msg)
            == [
                "https://github.com/Cmd-GZ/nonebot-plugin-shitbot",
                "https://manyacg.top/setu",
            ]
            * 3
        )
        assert get_multimedias_url(inner_content) == [
            "https://github.com/Cmd-GZ/nonebot-plugin-shitbot",
            "https://manyacg.top/setu",
        ]
        assert get_multimedias_url(msg, basetypes=[]) == []
        assert get_multimedias_url(inner_content, basetypes=[]) == []


# Unimplemented
class TestMsgModifyData:
    pass
