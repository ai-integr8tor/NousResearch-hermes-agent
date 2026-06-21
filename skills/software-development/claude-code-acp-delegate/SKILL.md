---
name: claude-code-acp-delegate
description: 通过 delegate_task 正确调用 Claude Code ACP 的规范 — 参数格式、模型别名映射、验证方法
---

# Claude Code ACP Delegate 调用规范

## 基本调用格式

```python
delegate_task(
    acp_command="claude-code-acp",   # 路由占位符，不需要 provider
    acp_args=["--model", "sonnet"],  # 可选，不填用默认
    goal="...",
    toolsets=[]                      # ACP 自己管理工具
)
```

## 关键点

1. **不需要 provider 参数** — `acp_command` 自动路由到 `claude-code-acp` provider
2. **acp_args 是列表** — `["--model", "sonnet"]` 不是字符串
3. **模型别名** — sonnet/opus/haiku 会被 `resolveModelPreference` 解析为完整模型名
4. **无 agent 工具** — ACP 自己管理工具，`toolsets=[]` 最高效

## 模型别名映射

`claude-agent-acp` 内部使用 `resolveModelPreference()` 做**子串匹配**，支持人类可读别名：

```javascript
// claude-agent-acp 源码注释：
// This lets callers use human-friendly aliases like
// "opus" or "sonnet" instead of full model IDs like "claude-opus-4-6".
```

### 匹配机制（3 级优先级）

1. **精确匹配**：`model.value === preference` 或 `displayName === preference`
2. **子串匹配**：`value.includes(preference)` 或 `preference.includes(value)`
3. **分词匹配**：tokenize 后评分（支持 `opus[1m]` 等格式）

### 推荐用法

```python
# ✅ 推荐：用别名（简洁、不依赖版本、由 claude-agent-acp 内部解析）
acp_args=["--model", "sonnet"]
acp_args=["--model", "opus"]
acp_args=["--model", "haiku"]

# ⚠️ 可用但不推荐：用完整模型名（绑定特定版本，仅调试/测试时用）
acp_args=["--model", "claude-sonnet-4-6"]
```

**推荐用别名的原因**：
1. **更简洁** — `sonnet` 比 `claude-sonnet-4-6` 短
2. **不依赖版本** — 如果 Claude SDK 更新模型名（如 `claude-sonnet-5`），别名仍然有效
3. **`claude-agent-acp` 内部处理** — 别名解析是 `claude-agent-acp` 的职责，hermes 不需要关心

**唯一例外**：需要**确定性绑定特定模型版本**（如测试、调试）时，用完整模型名。

## acp_args 可用参数

| 参数 | 值 | 说明 | 状态 |
|---|---|---|---|
| `--model` | `sonnet`/`opus`/`haiku` 或完整模型名 | 设置 ACP 模型 | ✅ 已测试 |
| `--effort` | `default`/`low`/`medium`/`high`/`xhigh`/`max` | 设置 effort level | ⚠️ 未调试成功，暂不可用 |
| `--permission-mode` | `auto`/`plan`/`acceptEdits` 等 | 设置权限模式 | ⚠️ 未调试成功，暂不可用 |

> **注意**：
> - `--model` 参数已验证可用（2026-06-16 真机测试）
> - `--effort` 参数：hermes 代码路径已通（正确发送 `session/set_config_option` 请求），但 `claude-agent-acp` 返回 "Internal error"，可能是 litellm 代理或 Claude SDK 不支持
> - `--permission-mode` 参数：未经测试验证

## 调用示例

### 最简调用（使用默认模型）
```python
delegate_task(
    acp_command="claude-code-acp",
    goal="Reply with exactly: ok",
    toolsets=[]
)
```

### 指定模型
```python
delegate_task(
    acp_command="claude-code-acp",
    acp_args=["--model", "sonnet"],
    goal="...",
    toolsets=[]
)
```

## 注意事项

1. **不需要填 provider** — `acp_command="claude-code-acp"` 自动触发路由
2. **不要传 acp_args 默认值** — `["--acp", "--stdio"]` 是 Copilot 的，Claude Code ACP 不需要
3. **子 agent 会消耗 token** — 简单任务用 `toolsets=[]` 减少开销
4. **600s timeout**：子 agent prompt 精简（3 步 verify 代替 7 步）可避免
5. **gateway 日志**：`ACP session model: sonnet (session=..., alive=False)` 显示实际配置的模型

## 验证方法

1. 检查 `~/.hermes/logs/agent.log` 中的 `ACP session model:` 日志
2. 检查 litellm 日志：`docker logs litellm --since=1m`
3. 直接调用 litellm API 验证模型路由

## 相关代码位置

- 路由逻辑：`tools/delegate_tool.py` `_build_child_agent()`
- ACP 客户端：`agent/claude_code_acp_client.py`
- 模型解析：`claude-agent-acp` 的 `resolveModelPreference()`

## Pitfalls

### Pitfall 1: 子 agent 600s timeout
- 原因：prompt 太长或 verify 步骤太多
- 解决：精简 prompt，3 步 verify（syntax/pytest/git log+status）
- 主 agent 独立 verify 全套

### Pitfall 2: 模型日志显示 hermes 模型而非 ACP 模型
- 原因：hermes 日志中的 `model=minimax-m3` 是 AIAgent 继承的模型
- 解决：方案 A — 从 `session/new` 响应读取 `configOptions` 缓存实际 ACP 模型
- 已实现：`agent/claude_code_acp_client.py` 的 `_get_acp_model()` 和 `_acp_config_options`

### Pitfall 3: git config local 覆盖 global
- 现象：amend author 后仍是旧 author
- 原因：subagent 残留 `git config --local user.name=nbot`
- 解决：amend 前 `git config --local --unset user.name && git config --local --unset user.email`

### Pitfall 4: gateway restart 中断 session
- 现象：`systemctl restart hermes-gateway` 后 session 被 killed
- 原因：Matrix bot 失联导致 session 中断
- 解决：发完消息后再 restart，或新 turn 验证

## 待验证项

- [ ] `--effort` 参数为什么返回 Internal error（检查 claude-agent-acp 或 litellm 代理实现）
- [ ] `--permission-mode` 参数是否生效
- [ ] 模型别名映射在 `claude-agent-acp` 版本更新后是否变化（依赖 Claude SDK 模型列表）
- [ ] 别名匹配优先级在边缘情况下的行为（如 `sonnet-4` 匹配到哪个模型）

## 更新历史

- 2026-06-16: 初始版本，基于 feat/claude-code-acp-provider 分支实践
- 2026-06-16: 澄清模型别名映射机制（子串匹配，非硬编码），推荐用别名而非完整模型名
- 2026-06-16: 测试 `--effort` 参数，返回 Internal error，标注为"未调试成功，暂不可用"
