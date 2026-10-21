# 业务理解规则

申请表、用户手册和软件设计说明书必须建立在真实项目证据上。模型阅读源码、README、需求文档、路由、接口、配置和可用截图后撰写正文，脚本不猜测业务或拼装叙述。

## 申请表与业务字段

保留 `product_positioning`、`industry`、`target_users`、`core_value`、`business_features`、`business_feature_details`、`application_purpose`、`main_functions`、`technical_characteristics`。

`application_purpose` 从真实的宏观场景说明目的，例如教学、科研实验和工程验证；`technical_characteristics` 在 100 字内具体说明处理机制和技术特点。固定申报值见 `application_fields.md`。

## 八章用户手册

必备字段：`manual_function_overview`、`manual_installation_config`、`manual_basics`、`manual_modules`、`manual_data_management`、`operation_flow`、`manual_usage_notes`、`faq`。具体大纲、字段结构、子节、截图、扩写提示词和分章页数见 [user_manual_structure.md](user_manual_structure.md)，撰写前必须读取。

`manual_modules` 用于第 4 章，取消原先 400 字上限，可包含多级 `subsections` 与 `tables`；`operation_flow` 是第 6 章完整任务案例，`faq` 独立为第 8 章。各章内容须围绕使用者准备、操作、结果判断和排错组织，避免反复解释系统实现。

先检查项目、用户截图与用户提供文档/PPT 中的可用图片；缺图时询问是否生成有源码证据的简单界面或保留预留位。图注只写功能或页面名称，来源和生成方式记录在截图清单中。

## 十章软件设计说明书

必备字段：`design_background`、`design_requirements`、`design_architecture`、`design_functions`、`design_interfaces`、`design_data`、`design_processing`、`design_reliability`、`design_deployment`、`design_use_cases`。具体大纲、展开方式、字段与分章页数见 [design_spec_structure.md](design_spec_structure.md)，撰写前必须读取。

各章以 `paragraphs` 总述及 `subsections` 分项展开，支持多级子节和表格。原“系统功能概述”扩展为第 4 章模块详细设计，说明职责、输入约束、核心处理、状态变化、输出与存储、异常边界和模块协作。接口、存储、核心处理、可靠性及部署独立成章。第 10 章最后保留典型流程与应用场景，不再使用旧顶层 `design_flow_scenarios` 字段。

## 两份 60 页文档的内容规划与确认

每份均为封面 1 页、目录 1 页、正文 58 页。先把每章拆成真实子节，列出对应证据、拟用图表与案例，形成 `草稿/文档内容规划.md`。预算只是参考，按项目复杂度调配。没有数据库、权限、网络接口、备份或自定义算法时，写实际工作方式与边界，不套用不存在的功能。

业务理解与 Markdown 草稿确认后生成 Word，更新目录并重新排版。少于 60 页时根据薄弱章节补充有依据的细节；超过时删去重复内容，保持完整性。任何正文变动后重跑页数核验。不得用空白页、放大字号行距、重复段落或图片凑页；不能用字数或分页符代替实际页数。

旧五章稿须补全新字段、重建内容规划并重新确认 business 与 markdown 阶段，保留用户原材料。证据不足时说明具体缺口，等待真实资料。三轮验证包括页数、章节、内容来源、截图与模块匹配、名称版本和逐页排版核对。
