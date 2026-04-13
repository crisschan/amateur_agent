# Amateur Agent - AI编程助手

⚠️ **重要安全警告**: 本项目目前仅用于开发和学习目的！
> 代理可以执行任意系统命令，请勿在不受信任的环境或生产环境中运行！
> 使用前请备份所有重要数据。

一个基于Ollama的交互式AI编程代理，具有强大的代码操作能力和可扩展的工具系统。

## 📋 项目简介

Amateur Agent是一个命令行工具，它将大型语言模型(LLM)与实用的开发工具相结合，让AI能够：
- 阅读和修改代码文件
- 执行系统命令
- 管理待办事项和任务
- 运行后台任务
- 加载扩展技能
- 生成子代理处理复杂任务

## 🏗️ 项目架构

### 核心组件

```
amateur_agent/
├── main.py                 # 程序入口，命令行参数解析
├── agent/                  # 核心代理模块
│   ├── agent.py           # 代理主类，组装所有功能
│   ├── config.py          # 配置管理
│   ├── loop.py            # 代理循环引擎
│   ├── memory/            # 记忆和上下文管理
│   │   └── compact.py     # 上下文压缩系统
│   └── tools/             # 工具模块
│       ├── filesystem.py  # 文件系统操作
│       ├── background.py  # 后台任务管理
│       ├── todo.py        # 待办事项
│       ├── tasks.py       # 持久化任务
│       ├── skills.py      # 技能加载器
│       ├── subagent.py    # 子代理生成
│       └── _safety.py     # 安全检查
└── skills/                # 技能目录
    └── code-review/       # 代码审查技能示例
```

### 技术栈
- **语言**: Python 3.10+
- **LLM集成**: LangChain + Ollama
- **依赖**: langchain-ollama, langchain-core, pyyaml

## 🚀 快速开始

### 1. 安装前提条件

确保你已经安装了：
- Python 3.10 或更高版本
- Ollama（用于运行本地LLM模型）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动Ollama服务

```bash
ollama serve
```

### 4. 模型（可选）

默认使用 `qwen2.5-coder` 模型，你也可以使用其他模型：

```bash
ollama pull qwen2.5-coder
```

### 5. 运行代理

```bash
# 使用默认配置
python main.py

# 指定模型
python main.py --model qwen2.5-coder

# 指定工作目录
python main.py --workdir /path/to/project
```

## 🎯 主要功能

### 1. 文件系统操作
代理可以直接操作你的代码文件：
- **读取文件**: 查看代码内容
- **写入文件**: 创建或修改文件
- **编辑文件**: 精确替换代码片段
- **执行命令**: 运行shell命令

### 2. 后台任务管理
长时间运行的任务可以在后台执行：
```python
# 代理可以这样使用工具：
background_run("npm install")
check_background()  # 检查任务状态
```

### 3. 待办事项管理
跟踪多步骤任务：
```python
todo(["1. 分析需求", "2. 设计架构", "3. 编写代码"])
```

### 4. 持久化任务存储
任务可以跨会话保存：
```python
task_create("重构认证模块", "改进安全性和性能")
task_update(1, status="进行中", progress=50)
```

### 5. 技能系统
通过SKILL.md文件扩展代理能力：
- 每个技能是一个目录，包含SKILL.md文件
- 代理可以动态加载技能指导
- 示例技能：代码审查、测试生成、文档编写

### 6. 子代理生成
复杂任务可以委托给子代理：
```python
task("分析这个项目的依赖关系", "需要详细的分析报告")
```

### 7. 上下文压缩
三种压缩机制防止上下文溢出：
1. **微压缩**: 每轮自动压缩旧工具结果
2. **自动压缩**: 超过阈值时生成摘要
3. **手动压缩**: 代理主动请求压缩

## ⚙️ 配置选项

### 命令行参数

```bash
python main.py [选项]

选项:
  --config FILE          agent.json配置文件路径（自动检测当前目录下的agent.json）
  --model MODEL          Ollama模型名称（覆盖OLLAMA_MODEL环境变量）
  --workdir DIR          工作目录（shell命令的cwd，默认为当前目录）
  --workspace DIR        文件操作边界（所有文件读写限制在此目录内）
  --no-todo         禁用内存待办事项列表
  --no-tasks         禁用持久化任务存储
  --no-skills            禁用技能加载
  --no-background        禁用后台执行
  --no-subagent       禁用子代理生成
  --no-compact           禁用上下文压缩
```

### 配置文件 agent.json

在项目根目录创建 `agent.json` 可以持久化配置，无需每次传命令行参数：

```json
{
  "model": "qwen2.5-coder",
  "workdir": ".",
  "workspace": "./src",
  "enable_background": false,
  "context_threshold": 30000
}
```

加载优先级：**默认值** < **agent.json** < **命令行参数**

### 环境变量

```bash
export OLLAMA_MODEL="qwen2.5-coder"      # 默认模型
export OLLAMA_BASE_URL="http://localhost:11434"  # Ollama服务地址
```

### 配置文件（代码中）

所有配置都通过 `AgentConfig` 类管理：
```python
from agent.config import AgentConfig

config = AgentConfig(
    model="qwen2.5-coder",
    temperature=0.2,
    max_tokens=4096,
    enable_todo=True,
    enable_tasks=True,
    # ... 其他配置
)
```

## 📖 使用指南

### 基本交互

1. **启动代理**：
   ```bash
   python main.py
   ```

2. **开始对话**：
   ```
   agent >> 帮我查看当前目录下的Python文件
   ```

3. **退出代理**：
   - 输入 `q` 或 `exit`
   - 按 `Ctrl+C` 或 `Ctrl+D`

### 示例用法

#### 1. 代码审查
```
agent >> 使用code-review技能审查main.py文件
```

#### 2. 文件操作
```
agent >> 读取config.py文件，然后创建一个备份
```

#### 3. 任务管理
```
agent >> 创建一个任务：学习Python异步编程
agent >> 更新任务1状态为进行中
agent >> 列出所有任务
```

#### 4. 后台任务
```
agent >> 在后台运行测试：pytest tests/
agent >> 检查后台任务状态
```

## 🔧 高级功能

### 1. 创建自定义技能

在 `skills/` 目录下创建新目录：

```bash
mkdir skills/my-skill
```

创建 `skills/my-skill/SKILL.md`：
```markdown
---
name: my-skill
description: 我的自定义技能
tags: custom, example
---

## 技能指导

这里是详细的指令...
```

### 2. 编程接口使用

```python
from agent.agent import Agent
from agent.config import AgentConfig

# 创建自定义配置
config = AgentConfig(
    model="qwen2.5-coder",
    workdir="/path/to/project",
    enable_background=False
)

# 初始化代理
agent = Agent(config)

# 单次查询
response = agent.run_query("列出所有Python文件")
print(response)

# 交互式会话
agent.repl()
```

## 🛡️ 安全特性

### 1. 危险命令检测
代理会自动检测并阻止危险的shell命令，防止意外损坏系统。

### 2. 路径安全
所有文件操作（read_file、write_file、edit_file）都会验证路径是否在 `workspace`（或 `workdir`）内，路径穿越会被拒绝。

bash 工具同样会扫描命令中的绝对路径，阻止访问 workspace 外的文件。

通过 `--workspace DIR` 或 `agent.json` 中的 `workspace` 字段配置边界。

### 3. 工具隔离
子代理仅继承文件系统工具和技能加载工具，其他危险操作默认禁用。

## 📊 性能优化

### 上下文管理
- **微压缩**: 每轮压缩旧工具结果，减少内存占用
- **自动压缩**: 超过5万字符时自动生成摘要
- **保留最近3个工具结果**: 保持上下文连贯性

### 异步执行
后台任务在独立线程中运行，不阻塞主对话。

## ⚠️ 已知问题与限制

> 当前项目处于实验开发阶段，存在以下已知限制：

1. **无限循环风险**: 代理循环没有最大执行次数限制，可能进入无限工具调用循环
2. **安全防护有限**: 危险命令检测为基础字符串匹配，可被多种方式绕过
3. **内存增长**: 长时间运行会话会持续增长内存占用
4. **无错误恢复**: 未实现工具调用失败的重试和熔断机制
5. **缺少沙箱**: 目前没有命令执行隔离和权限限制

我们正在积极改进这些问题，欢迎参与贡献。

---

## 🐛 故障排除

### 常见问题

#### 1. 连接Ollama失败
```bash
# 检查Ollama服务状态
ollama list

# 启动Ollama服务
ollama serve
```

#### 2. 模型不存在
```bash
# 下载所需模型
ollama pull qwen2.5-coder
```

#### 3. 权限错误
```bash
# 确保工作目录有正确权限
chmod -R 755 /path/to/workdir
```

#### 4. 依赖缺失
```bash
# 重新安装依赖
pip install -r requirements.txt --force-reinstall
```

## 🎨 自定义和扩展

### 1. 添加新工具
在 `agent/tools/` 目录创建新模块，实现工具函数并在 `agent.py` 中注册。

### 2. 修改系统提示
编辑 `agent.py` 中的 `_build_system()` 方法。

### 3. 调整压缩策略
修改 `config.py` 中的压缩参数：
```python
context_threshold = 50_000  # 自动压缩阈值
keep_recent_tools = 3       # 保留的最近工具结果数
```

## 📚 学习资源

### 相关文档
- [LangChain文档](https://python.langchain.com/)
- [Ollama文档](https://ollama.ai/)
- [Python dataclasses](https://docs.python.org/3/library/dataclasses.html)

### 示例技能
查看 `skills/code-review/SKILL.md` 了解技能文件格式。

## 🤝 贡献指南

1. Fork项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建Pull Request

## 📄 许可证

本项目采用MIT许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- LangChain团队提供的优秀框架
- Ollama项目让本地LLM运行变得简单
- 所有贡献者和用户

---

**注意**: 这是一个开发中的项目，也是学习Agent过程中的实验，功能可能会发生变化。请在使用前备份重要数据。