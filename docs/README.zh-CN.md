# BTLX Editor Core 中文文档

[English README](../README.md) · [发行说明](RELEASE_NOTES_0.1.0a1.md) · [兼容性报告](COMPATIBILITY.md) · [源码来源说明](SOURCE_PROVENANCE.md)

## 1. 项目是什么

**BTLX Editor Core** 是一个使用 Python 编写的轻量级二进制结构解析与编辑核心，重点处理 Protobuf wire 格式的数据。

它的设计目标不是“把所有二进制都解出来”，而是在调用方提供结构描述的前提下，尽可能准确地读取和修改已知字段，同时保留没有修改、甚至尚不理解的原始字节。

它适合作为桌面编辑器、数据检查工具或其他开发工具的底层库。

> 当前版本为 Alpha 0.1.0a1。它是一个可复用的 Python 库，不是完整的游戏编辑器，也不包含 GUI、独立 CLI 或 MCP 服务。

## 2. 核心能力

| 能力 | 说明 |
|---|---|
| 无损 wire 解析 | 保留原始字段字节、字段顺序、重复字段、未知字段和非规范 varint 编码 |
| 外部描述符 | 使用调用方提供的描述符报告，不内置特定游戏的字段定义 |
| 结构化读取 | 按描述符解析字段类型、嵌套消息和字段路径 |
| 精确修改 | 修改目标字段时，尽量只重新编码目标字段及其父消息长度前缀 |
| 事务式编辑 | 支持多操作编辑计划；全部操作和写后检查成功后才返回新字节 |
| 旧数据保护 | 可通过源数据 SHA-256 前置条件拒绝对过期数据执行编辑 |
| 轻量依赖 | 运行时仅使用 Python 标准库 |

### 支持的编辑操作

- `assert`：检查字段当前值是否符合预期。
- `set`：修改已知字段的值。
- `add`：向消息添加描述符已知的字段。
- `remove`：移除指定字段出现项。
- `clone`：复制指定字段出现项。
- `move`：调整重复字段的出现顺序。
- `replace-message`：按描述符重建指定的嵌套消息。

这些操作只针对描述符可识别的字段。未知字段不会因为“看起来像某种数据”就被自动赋予类型或语义。

## 3. 安装

### 环境要求

- Python 3.11 或更高版本。
- 从源码构建时需要可用的 setuptools 构建环境。
- 运行库没有第三方依赖。

### 从 GitHub 源码安装

当前尚未发布到 PyPI。可以直接克隆源码安装：

```bash
git clone https://github.com/hellow0rld-lyh/-btlx-editor-core.git
cd ./-btlx-editor-core
python -m pip install .
```

### 从 Wheel 安装

如果已经取得发行包中的 `.whl` 文件：

```bash
python -m pip install btlx_editor_core-0.1.0a1-py3-none-any.whl
```

### 从源码包安装

如果取得 `.tar.gz` 源码发行包：

```bash
python -m pip install btlx_editor_core-0.1.0a1.tar.gz
```

## 4. 快速上手

### 4.1 只做底层 wire 解析

```python
from btlx_core import parse_message, serialize_preserving

original = bytes.fromhex("08 07 10 2A")
message = parse_message(original)

# 未修改字段使用原始编码字节重新输出。
assert serialize_preserving(message) == original
```

这里的 `08 07` 和 `10 2A` 是两个合成的 Protobuf wire 字段。示例不依赖任何真实游戏存档或资源。

### 4.2 使用外部描述符编辑字段

结构化编辑需要调用方提供描述符。下面是最小化示意：

```python
import hashlib
from btlx_core import ProfileSpec, profile_from_reports, parse_btlx, apply_edit_plan

spec = ProfileSpec("demo-v1", "Synthetic", "v1", "", "")
descriptor = {
    "candidates": [{
        "messages": [{
            "name": "Root",
            "fullName": "Demo.Root",
            "fields": [{
                "name": "Score",
                "number": 1,
                "type": "int32",
                "label": "optional",
            }],
        }],
    }],
}
profile = profile_from_reports(
    spec,
    descriptor,
    {"rootMessage": {"fullName": "Demo.Root", "status": "Synthetic"}},
)

source = bytes.fromhex("08 07 9A 03 02 08 01")
plan = {
    "schema": "EasyTechBTLXEditPlan/v1",
    "profile": "demo-v1",
    "sourceSha256": hashlib.sha256(source).hexdigest(),
    "operations": [{"op": "set", "path": "Score", "value": 9}],
}

edited, receipt = apply_edit_plan(source, profile, plan)
assert parse_btlx(edited, profile).get_value("Score") == 9
assert receipt["postEditRoundTripExact"]
```

完整的可运行样例位于 [`examples/synthetic_roundtrip.py`](../examples/synthetic_roundtrip.py)，隔离安装测试位于 [`smoke_test.py`](../smoke_test.py)。

## 5. 无损保证的边界

本项目的“无损”指：**对于未被编辑的 wire 字段，序列化时沿用解析得到的原始编码字节**。这包括：

- 未知字段；
- 重复出现的字段；
- 原始字段顺序；
- 非规范 varint；
- 未被选中的嵌套消息内容。

当修改某个字段时，该字段及其必要的父消息长度前缀需要重新编码。因此不能把“整份文件所有字节永远不变”理解为编辑后的目标。

此外，无损 wire 解析不等于游戏语义已经恢复。字段名、字段含义、版本兼容性和游戏运行效果仍取决于独立证据。

## 6. 主要 API

| API | 用途 |
|---|---|
| `parse_message(data)` | 解析原始 Protobuf wire 消息 |
| `serialize_preserving(message)` | 按原始字段字节序列化 |
| `ProfileSpec(...)` | 声明描述符配置的身份信息 |
| `profile_from_reports(...)` | 根据外部描述符报告创建结构配置 |
| `parse_btlx(data, profile)` | 按配置解析 BTLX 消息 |
| `semantic_diff(a, b, profile)` | 对结构化消息进行比较 |
| `apply_edit_plan(data, profile, plan)` | 执行受约束的事务式编辑 |

## 7. Python 兼容性与测试

当前包声明支持 Python 3.11 及以上。已通过的 GitHub Actions 环境：

| 系统 | Python | 状态 |
|---|---:|---|
| Ubuntu | 3.11 | PASS |
| Ubuntu | 3.12 | PASS |
| Ubuntu | 3.13 | PASS |
| Ubuntu | 3.14 | PASS |
| Windows | 3.14 | PASS |

CI 使用合成数据执行回归测试、安装测试和示例。它们验证的是 Python 库行为，不代表已经在特定游戏版本、真实存档或设备上验收。

本地运行测试：

```bash
python -m unittest discover -s tests -v
python examples/synthetic_roundtrip.py
python smoke_test.py .test-install
```

## 8. 构建发行包

在仓库根目录执行：

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
```

构建后 `dist/` 中应包含：

- `.whl`：适合直接安装的二进制发行格式（本项目为纯 Python，因此是 `py3-none-any`）。
- `.tar.gz`：源码发行包，包含源码、文档、示例和合成测试。

SHA-256 校验值应随发行文件一并保存。不要在没有确认版本号、许可证和发布授权的情况下上传到 PyPI。

## 9. 项目边界与注意事项

本仓库不包含：

- 原版游戏 APK、SO、DEX、地图、资源或战斗数据；
- 未获再分发授权的描述符、私有语料和逆向证据；
- 游戏专用 native 补丁或内置的特定游戏版本配置；
- GUI、完整游戏编辑器、独立 CLI 或 MCP 服务。

不要仅凭 wire 字段编号或解析成功就推断游戏行为。请只使用你有权处理的数据和描述符；游戏专用结论应保留游戏名称、版本和证据边界。

## 10. 许可证

本项目使用 **GNU LGPL-3.0-or-later**。

- `COPYING`：GNU GPLv3 基础许可证文本。
- `COPYING.LESSER`：GNU LGPLv3 补充条款。
- 源码文件包含相应 SPDX 许可证标识。

修改或再分发时请保留版权与许可证声明，并遵守 LGPL 的适用要求。原版游戏名称、商标、素材及其他知识产权不因本项目许可证而转让。

## 11. 当前版本

**0.1.0a1 — Alpha**

这是早期测试版，公共 API、编辑计划格式和行为细节在稳定版发布前仍可能调整。当前尚未上传 PyPI，也未宣称支持任何特定游戏版本的完整读写兼容性。

问题反馈请附上最小化的合成复现，不要上传游戏原始资源、私人数据、密钥或其他不适合公开的文件。