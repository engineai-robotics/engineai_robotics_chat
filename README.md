# EngineAI Robotics Chat

[中文](README_CN.md) | English

This repository is maintained by EngineAI. It provides a reference implementation of on-robot speech for developers integrating audio capture, dialogue, and speech services on real robots.

## Supported Robots

| Robot | Support |
| --- | --- |
| PM01 | ✓ |
| T800 | ✗ |

## Overview

Main capabilities:

- **Capture and playback** — Reads the onboard or an external microphone and plays synthesized speech through the speaker. Multi-channel audio is kept until mixdown, so voice channels stay separate from speaker loopback.
- **Local retrieval** — Supplies local documents for retrieval-augmented dialogue.

## Repository Structure

```text
src/engineai_robotics_chat/
├── audio/                 # Sound devices, multi-channel frames, and playback
├── dialog/                # Session control and tool calls
├── providers/             # Third-party API integration
└── knowledge/             # Local BM25 retrieval
examples/                  # Runnable examples and their documentation
data/                      # Example data
```

## Installation

From the repository root:

```bash
pip install -e ".[rag]"
```

`rag` installs the local-retrieval dependencies. For an install without local retrieval, run `pip install -e .`. `requirements.txt` lists the full dependency set.

## Examples

The runnable example is Volcengine end-to-end dialogue. See [examples/volcengine/README.md](examples/volcengine/README.md).

## License

This project is licensed under the [BSD 3-Clause License](LICENSE.txt). Copyright Shenzhen Zhongqing Robot Technology Co., Ltd. ("EngineAI").
