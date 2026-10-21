# EngineAI Robotics Chat

中文 | [English](README.md)

本仓库由众擎机器人维护，仓库提供机器人端语音能力的参考实现，供开发者在真机上接入采集、对话和语音服务。

## 支持机型

| 机型 | 支持情况 |
| --- | --- |
| PM01 | ✓ |
| T800 | ✗ |

## 概述

仓库的主要功能

- **采集与播放**：读取机载或外接麦克风，并将合成语音输出到扬声器。多声道数据在混音前保留，以便区分人声与扬声器回采。
- **本地检索**：为对话提供本地资料，实现对话中的 RAG 功能。

## 仓库结构

```text
src/engineai_robotics_chat/
├── audio/                 # 声卡、多声道帧与播放
├── dialog/                # 会话控制与工具调用
├── providers/             # 第三方 API 调用
└── knowledge/             # 本地 BM25 检索
examples/                  # 可运行示例及对应说明
data/                      # 示例数据
```

## 安装

在仓库根目录执行：

```bash
pip install -e ".[rag]"
```

`rag` 为本地检索依赖。不使用本地检索时，执行 `pip install -e .`。`requirements.txt` 列出当前全部依赖。

## 示例

当前可运行的示例为火山引擎端到端对话，使用说明见 [examples/volcengine/README.md](examples/volcengine/README.md)。

## 许可证

本项目基于 [BSD 3-Clause 许可证](LICENSE.txt) 开源。版权归深圳市众擎机器人科技有限公司（Shenzhen Zhongqing Robot Technology Co., Ltd.，"EngineAI"）所有。
