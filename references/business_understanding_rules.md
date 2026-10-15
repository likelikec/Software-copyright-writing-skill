# 业务理解规则

申请表、用户手册和软件设计说明书必须建立在项目真实证据上。模型应阅读源码、README、PRD/BRD、页面文案、路由、接口、配置和用户提供的截图，再生成业务理解 JSON；脚本不得用关键词或固定范本猜测业务。

## 必备字段

业务理解模型稿至少包含：

- `product_positioning`、`industry`、`target_users`、`core_value`
- `business_features`、`business_feature_details`、`operation_flow`
- `application_purpose`、`main_functions`、`technical_characteristics`
- `manual_function_overview`
- `manual_installation_config`
- `manual_modules`
- `manual_usage_notes`
- `faq`
- `design_background`、`design_architecture`、`design_functions`、`design_use_cases`、`design_flow_scenarios`

`application_purpose` 应从宏观真实场景说明软件开发目的，例如面向测试教学、科研实验、工程验证或其他项目证据支持的场景，不得只写软件名称。

`technical_characteristics` 必须在申请表限制的 100 字内尽量具体地说明真实技术机制、处理方式和差异化特点，不能只罗列框架名或空泛评价。

## 用户手册字段

用户手册固定五章，字段含义如下：

- `manual_function_overview`：第 1 章正文，先总览，再介绍各功能。
- `manual_installation_config`：第 2 章正文，可为段落数组，或包含 `paragraphs` 与 `requirements` 表格的对象。
- `manual_modules`：第 3 章功能模块。每项包含 `title`、`body`、`purpose`、`usage` 或 `usage_scenario`、`entry`、`visible_elements`、`operation_steps`、`validation_rules`、`feedback`、`boundary`、`screenshot`、`evidence`。
- `operation_flow`：第 4 章典型流程正文，必须反映真实操作顺序。
- `manual_usage_notes`：第 5 章注意事项正文。
- `faq`：第 5 章常见问题数组，每项含 `question` 和 `answer`。

模块正文 `body` 由模型直接撰写，通常为两段、120 至 220 字，复杂模块最多 400 字。脚本不根据其他字段拼装句子、不改写正文，只校验章节、长度、截图和必备信息。

## 用户截图

截图只允许来自用户放入 `软件著作权申请资料/用户截图/` 的 PNG/JPG/JPEG/WebP，脚本负责整理到 `截图/` 并在手册中引用。缺图时保留可见预留文字，不能用无关图片替代。

## 设计说明书字段

设计说明书由模型依据源码和项目证据撰写，正文至少包含：

1. `design_background`：背景。
2. `design_architecture`：系统架构设计，包含架构设计、接口设计、数据库设计以及项目真实需要的后续小节。
3. `design_functions`：系统功能概述，先总览，再分项展开。
4. `design_use_cases`：系统关键用例描述，针对典型功能写用例。
5. `design_flow_scenarios`：典型流程与应用场景。

设计说明书的首页、目录和样式由内置模板提供；模型只填写项目正文，不能把模板样例项目的事实带入新项目。

## 确认与验证

业务理解生成后必须停止，等待用户确认。确认前不得生成申请表、用户手册或设计说明书。生成材料后还要分别检查：字段是否来自项目证据、截图是否对应模块、软件名称和版本号是否一致、设计说明书是否残留样例项目内容。
