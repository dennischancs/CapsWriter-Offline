# coding: utf-8
"""
文本格式化工具

提供中英文混排文本的空格调整功能。
主要用于调整识别结果中中英文之间的空格。
"""

from __future__ import annotations
import re
from typing import Match

# 匹配中文字符包围的英文/数字/符号序列
_EN_IN_ZH_PATTERN = re.compile(r"""(?ix)
    ([\u4e00-\u9fa5])?                  # 左侧：中文
    (                                   # 中间：英文数字及常用技术符号序列
        [a-z0-9+#]                      # 起头：字母、数字、+、#
        [a-z0-9\s'.,!+#/_:@%&?-]*       # 中间：允许空格和更多符号 (将 - 移至末尾)
        [a-z0-9+#%]                     # 结尾：字母、数字、+、#、%
        |
        [a-z0-9]                        # 或者：单个字母或数字
    )
    ([\u4e00-\u9fa5])?                  # 右侧：中文
""")


def _attaches_to_letters(word: str) -> bool:
    """单字母后面的 FP16 / 16 还是型号，多位纯数字之间的空格不是。"""
    if not word:
        return False
    if word.isdigit():
        return True
    return word[0].isalpha() and any(char.isdigit() for char in word)


def _merge_parts(words: list[str]) -> str:
    """合并拼出来的字母，但不要把已经分开的数字再粘成一个。

    C O M F Y → COMFY，F P 16 → FP16。
    5 5 10、350 100 这种是两个数，空格要留着。
    """
    if len(words) <= 1:
        return words[0] if words else ''

    merged: list[str] = []
    index = 0
    while index < len(words):
        word = words[index]
        if len(word) == 1 and word.isalpha():
            end = index + 1
            while end < len(words) and len(words[end]) == 1 and words[end].isalpha():
                end += 1
            piece = ''.join(words[index:end])
            if end < len(words) and _attaches_to_letters(words[end]):
                piece += words[end]
                end += 1
            merged.append(piece)
            index = end
            continue
        if len(word) == 1 and word.isdigit():
            end = index + 1
            while end < len(words) and len(words[end]) == 1 and words[end].isdigit():
                end += 1
            merged.append(''.join(words[index:end]))
            index = end
            continue
        merged.append(word)
        index += 1
    return ' '.join(merged)


def _replacer(match: Match) -> str:
    left, raw, right = (match.group(i) or '' for i in (1, 2, 3))
    center = _merge_parts(raw.strip().split())
    has_alpha = bool(re.search(r'[a-zA-Z]', center))

    if left and has_alpha:
        left += ' '
    if right and has_alpha:
        right = ' ' + right

    return f'{left}{center}{right}'



def adjust_space(text: str) -> str:
    """
    调整中英文/数字之间的空格

    1. 在中文和英文、数字之间插入空格。
    2. 将连续的单个英文字母（如 "A B C"）合并为 "ABC"。
    3. 支持常用技术符号如 C++, TCP/IP, 100%。

    因为正则匹配不重叠，同一中文字符只能当一个边界。
    迭代替换可解决 "C盘Windows" 这种链式场景：
      第1轮 → "C 盘Windows 目" (盘被 C 用掉了)
      第2轮 → "C 盘 Windows 目" (盘现在可作 Windows 的左边界)

    Args:
        text: 输入文本

    Returns:
        优化后的文本
    """
    for _ in range(3):
        new_text = _EN_IN_ZH_PATTERN.sub(_replacer, text)
        if new_text == text:
            break
        text = new_text
    return text


if __name__ == "__main__":
    # 测试用例
    test_cases = [
        # 基础中英空格
        "这是hello世界",
        "hello世界",
        "这是一个iPhone手机",
        "这是一个iPhone15手机",
        "Mixed中文English测试",
        # 链式边界（同一中文字符需作左右两个边界）
        "文件在C盘Windows目录下",
        # 拼读合并
        "尝试一下 C O M F Y U I怎么样",
        "你可以试一下 F P 32 和 F P 16 如何",
        "试一下F P16的效果",
        # 英文句子嵌中文
        "他说I love you这句话很浪漫",
        "请执行git commit操作",
        # 纯英文/符号不变
        "I have a phone",
        "C++是非常强的语言",
        "TCP/IP协议",
        "100%的安全",
        "C# 也是一门语言",
        "数字123也会测试",
    ]

    print(f"{'Original Text':<25} | {'Adjusted Text'}")
    print("-" * 60)
    for text in test_cases:
        print(f"{text:<25} | {adjust_space(text)}")

