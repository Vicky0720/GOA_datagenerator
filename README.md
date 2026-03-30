# 游戏数据生成器说明书

## 1. 文件用途

[`data_generator.py`](./data_generator.py) 用于生成一套游戏业务模拟数据，输出以下 5 个 CSV 文件：

- `users.csv`：用户静态属性
- `events.csv`：用户行为事件
- `payments.csv`：用户支付记录
- `campaigns.csv`：运营活动计划表
- `event_calendar.csv`：特殊事件影响日历

这份生成器适合用于：

- 数据分析练习
- 指标看板联调
- SQL / Python 建模演示
- 留存、付费、活动影响的模拟测试


## 2. 整体生成逻辑

生成流程分为 5 步：

1. 生成用户基础档案
2. 按用户逐日生成行为事件
3. 基于行为强度生成支付记录
4. 生成固定的活动计划表
5. 生成特殊事件日历并输出汇总

可以把逻辑理解成下面这条链路：

`用户画像 -> 活跃概率 -> 事件数量/事件类型 -> 活动强度 -> 付费概率 -> 支付金额`


## 3. 输出表说明

### 3.1 `users.csv`

字段包括：

- `user_id`：用户编号
- `register_date`：注册时间
- `country`：国家
- `device`：设备平台
- `channel`：获客渠道
- `persona`：用户画像

这是后续事件和支付数据的基础维表。

### 3.2 `events.csv`

字段包括：

- `user_id`
- `event_time`
- `event_type`
- `session_length`

其中事件类型固定为：

- `login`
- `play`
- `mission_complete`
- `level_up`
- `quit`

### 3.3 `payments.csv`

字段包括：

- `user_id`
- `payment_time`
- `amount`
- `product_type`

支付记录不是独立随机生成，而是依赖用户事件活跃度和活动加成。

### 3.4 `campaigns.csv`

这是固定活动表，主要用于模拟业务背景，不直接参与算法计算。

### 3.5 `event_calendar.csv`

这是特殊事件配置导出的平铺结果，用来解释某段时间 DAU、付费或退出率为什么发生变化。


## 4. 用户生成逻辑

用户由 `generate_users()` 生成，核心是“按概率抽样”。

### 4.1 用户数量

由 `n_users` 控制，默认是 `2500`。

### 4.2 注册时间

用户注册时间在观察期开始日到注册截止日之间均匀随机分布。

默认：

- 观察期开始：`2025-10-01`
- 注册截止：`2025-12-31`

这意味着：

- 越早注册的用户，可被观察的天数越多
- 越晚注册的用户，累计事件和累计付费往往更少

### 4.3 用户画像

默认画像及占比：

- `whale`：8%
- `engaged_nonpayer`：27%
- `casual`：45%
- `at_risk`：20%

画像决定后续的：

- 日活概率
- 单日事件数
- 平均会话时长
- 基础付费概率
- 平均支付次数

### 4.4 国家、设备、渠道

这些字段也通过概率抽样生成。

默认国家分布：

- `SG`：45%
- `MY`：20%
- `ID`：20%
- `PH`：15%

默认设备分布：

- `ios`：40%
- `android`：60%

默认渠道分布：

- `organic`：35%
- `ads`：40%
- `referral`：15%
- `influencer`：10%


## 5. 行为事件生成逻辑

行为由 `generate_events()` 生成，逻辑是“按用户逐天判断是否活跃，如果活跃则生成若干事件”。

### 5.1 每天是否活跃

每天先计算一个活跃概率 `activity_prob`，公式可以近似理解为：

`画像基础活跃率 × 渠道活跃系数 × 渠道留存系数 × 国家活跃系数 × 特殊事件活跃系数 × 时间修正`

其中时间修正包括：

- `at_risk` 用户会随时间衰减
- 新注册前 7 天会有 1.15 倍新手活跃提升

最后活跃概率会被限制在 `0.01 ~ 0.98` 之间。

### 5.2 各画像基础活跃参数

默认如下：

- `whale`
  - `day_active_prob = 0.75`
  - `avg_events_per_active_day = 5.0`
  - `session_mean = 42`
- `engaged_nonpayer`
  - `day_active_prob = 0.65`
  - `avg_events_per_active_day = 4.0`
  - `session_mean = 35`
- `casual`
  - `day_active_prob = 0.32`
  - `avg_events_per_active_day = 2.0`
  - `session_mean = 18`
- `at_risk`
  - `day_active_prob = 0.50`
  - `avg_events_per_active_day = 3.0`
  - `session_mean = 20`

### 5.3 活跃后生成多少事件

若某天被判定为活跃，则事件数量由泊松分布生成：

`n_events ~ Poisson(avg_events_per_active_day × event_activity_mult)`

并至少为 1。

所以：

- 提高 `avg_events_per_active_day` 会明显抬高事件量
- 提高活动期 `activity_mult` 会同时提升“活跃人数”和“活跃用户当天的事件量”

### 5.4 事件类型如何分布

不同画像使用不同的事件类型概率。

例如：

- `whale` 更偏向 `play`
- `casual` 和 `at_risk` 的 `quit` 占比更高

特殊事件会通过 `quit_mult` 改变 `quit` 事件权重，再重新归一化。

因此：

- 提高 `quit_mult` 会提高退出事件占比
- 降低 `quit_mult` 会让行为更“健康”

### 5.5 会话时长如何生成

会话时长使用正态分布生成：

`session_length ~ Normal(session_mean × country_session_mult × event_session_mult, 8)`

并限制最小为 1。

所以：

- 国家和活动会影响会话时长
- 波动标准差当前固定是 `8`
- 如果你想让时长更稳定，可把 `8` 调小
- 如果你想让用户行为更离散，可把 `8` 调大


## 6. 支付生成逻辑

支付由 `generate_payments()` 生成，核心思想是“先根据画像和活跃度判断会不会付费，再生成支付次数和金额”。

### 6.1 付费概率如何计算

基础付费概率来自画像，然后叠加行为活跃度。

代码中的近似逻辑如下：

- `whale`：`pay_prob_base + activity_count / 300`，上限 `0.95`
- `engaged_nonpayer`：`pay_prob_base + activity_count / 1000`，上限 `0.25`
- `casual`：`pay_prob_base + activity_count / 1200`，上限 `0.30`
- `at_risk`：`pay_prob_base + activity_count / 1500`，上限 `0.12`

然后再乘以：

- 渠道付费系数 `payment_mult`
- 国家付费概率系数 `payment_prob_mult`
- 最近事件所在活动窗口带来的 `event_payment_boost`

最终结果再限制在 `0.0 ~ 0.99`。

这意味着：

- 事件越多，付费概率越高
- `whale` 对活跃度最敏感
- `at_risk` 即使活跃起来，付费上限也依然偏低

### 6.2 支付次数如何生成

一旦该用户被判定为付费用户，支付次数由泊松分布生成：

`n_payments ~ Poisson(avg_payments)`

若最近活动的 `payment_mult > 1.2`，则 `avg_payments` 额外乘以 `1.15`。

默认画像的平均支付次数：

- `whale`：4.0
- 其他画像：1.0

### 6.3 支付时间如何确定

如果用户有事件记录，支付时间从该用户已有事件时间中随机抽样；
如果没有事件记录，则在注册后 14 天内随机生成一个支付时间。

这会让支付记录和行为记录在时间上更自然地对齐。

### 6.4 支付金额如何确定

先根据画像选择一个离散金额档位：

- `whale`：`[12, 25, 60, 120]`
- `engaged_nonpayer`：`[3, 5, 8, 15]`
- `casual`：`[3, 6, 12, 20]`
- `at_risk`：`[2, 4, 6, 10]`

之后再做几层修正：

- `whale` 有 25% 概率乘以 `1.5` 或 `2.0`
- 再乘以国家金额系数 `payment_amt_mult`
- 若活动期 `payment_mult > 1.2`，有 35% 概率再乘以 `1.10`

最后四舍五入到两位小数。

### 6.5 商品类型如何确定

`product_type` 由金额区间决定：

- 金额小于等于 6：更偏向 `starter_bundle`
- 金额在 6 到 20 之间：`battle_pass`、`gem_pack` 更常见
- 金额大于 20：`vip_bundle` 概率更高


## 7. 渠道、国家、活动三类修正器

这部分是整个生成器最重要的“调参杠杆”。

### 7.1 渠道修正 `CHANNEL_EFFECTS`

每个渠道有三个核心系数：

- `activity_mult`：影响活跃概率
- `payment_mult`：影响付费概率
- `retention_mult`：影响每日持续活跃能力

默认特征：

- `organic`：整体最平稳
- `ads`：活跃和付费偏低，留存也偏低
- `referral`：活跃、付费、留存都较好
- `influencer`：活跃高，但留存和付费一般

如果你想模拟：

- 买量用户质量差：下调 `ads.retention_mult`
- 裂变用户质量高：上调 `referral.payment_mult`
- 达人带来高曝光低转化：上调 `influencer.activity_mult`，下调 `influencer.payment_mult`

### 7.2 国家修正 `COUNTRY_EFFECTS`

每个国家有四个核心系数：

- `activity_mult`
- `payment_prob_mult`
- `payment_amt_mult`
- `session_mult`

默认设计体现的是：

- `SG` 支付概率和金额较高
- `ID`、`PH` 活跃不低，但支付金额偏低
- `MY` 作为中间水平

如果你想模拟：

- 某国家更高 ARPPU：提高 `payment_amt_mult`
- 某国家玩家更爱玩但不爱付费：提高 `activity_mult`，降低 `payment_prob_mult`
- 某国家在线时长更长：提高 `session_mult`

### 7.3 特殊事件修正 `SPECIAL_EVENTS`

特殊事件可以按时间窗口叠加影响：

- `activity_mult`
- `payment_mult`
- `session_mult`
- `quit_mult`

并支持定向到：

- `target_personas`
- `target_channels`
- `target_countries`

当前内置的 4 个事件分别模拟了：

- 节庆活动：活跃和付费整体上升
- 首充包活动：定向刺激高活跃非付费用户转化
- 服务器事故：活跃和付费下降，退出上升
- 召回活动：定向提升流失风险用户回流

如果你想模拟更真实的运营场景，这里是最值得扩展的配置区。


## 8. 哪些参数影响哪些结果

下面这张“调参对照表”最适合日常使用。

### 8.1 想提高 DAU

优先调整：

- `PERSONA_PROBS` 中高活跃画像占比
- `get_persona_base_params()` 里的 `day_active_prob`
- `CHANNEL_EFFECTS[*].activity_mult`
- `CHANNEL_EFFECTS[*].retention_mult`
- `SPECIAL_EVENTS[*].activity_mult`

### 8.2 想提高事件量

优先调整：

- `avg_events_per_active_day`
- `SPECIAL_EVENTS[*].activity_mult`
- 观察期长度 `obs_end - obs_start`
- 用户数量 `n_users`

### 8.3 想提高留存感

优先调整：

- `retention_mult`
- `at_risk` 用户衰减逻辑
- 新手前 7 天提升倍数 `1.15`
- 降低 `quit_mult`

### 8.4 想提高付费率

优先调整：

- `pay_prob_base`
- 活跃度对付费的加成分母，如 `/300`、`/1000`
- `CHANNEL_EFFECTS[*].payment_mult`
- `COUNTRY_EFFECTS[*].payment_prob_mult`
- `SPECIAL_EVENTS[*].payment_mult`

### 8.5 想提高 ARPPU / 收入

优先调整：

- `get_amount_scale()` 中各画像金额档位
- `COUNTRY_EFFECTS[*].payment_amt_mult`
- `whale` 的倍数放大概率与倍数范围
- `choose_product_type()` 的映射逻辑

### 8.6 想让退出率更高或更低

优先调整：

- `get_event_type_probs()` 中各画像原始 `quit` 权重
- 特殊事件中的 `quit_mult`


## 9. 推荐调参方法

建议按下面顺序调参，比较稳：

1. 先调用户结构
2. 再调行为强度
3. 再调付费
4. 最后调特殊事件

原因是：

- 用户结构决定总体盘子
- 行为强度决定 DAU 和事件量
- 付费依赖行为结果
- 活动效果更适合作为局部波动修饰

如果一上来就猛调活动系数，容易出现“局部峰值很夸张，但底盘不合理”的问题。


## 10. 常见场景调参示例

### 10.1 想做“买量盘”

建议：

- 提高 `CHANNEL_PROBS` 中 `ads`
- 降低 `ads.retention_mult`
- 降低 `ads.payment_mult`
- 提高 `n_users`

预期结果：

- 新增多
- DAU 有量
- 留存偏弱
- 付费率偏低

### 10.2 想做“高价值成熟盘”

建议：

- 提高 `whale` 和 `engaged_nonpayer` 占比
- 提高 `SG` 占比
- 提高 `referral` 占比
- 提高 `whale` 金额档位

预期结果：

- 事件量高
- 付费率高
- ARPPU 高
- 收入更集中

### 10.3 想做“流失告警场景”

建议：

- 提高 `at_risk` 占比
- 加快 `at_risk` 衰减
- 添加持续数天的 `server_incident`
- 提高 `quit_mult`

预期结果：

- DAU 下滑
- `quit` 占比上升
- 支付减少

### 10.4 想做“活动拉收场景”

建议：

- 增加一个面向 `engaged_nonpayer` 或 `whale` 的活动
- 提高 `payment_mult`
- 稍微提高 `activity_mult`
- 保持 `quit_mult <= 1`

预期结果：

- 活动期付费率提升
- 付费金额提升
- 行为不会明显恶化


## 11. 运行参数说明

脚本现在支持“配置文件 + 命令行覆盖”的方式。

默认配置文件是 [`generator_config.json`](./generator_config.json)。

你可以直接在这个文件中配置几乎所有核心参数，包括：

- 生成用户数量
- 观察期起止时间
- 注册截止时间
- 画像、国家、设备、渠道分布
- 各画像的活跃、付费、金额档位、事件类型概率
- 渠道和国家修正系数
- 活动事件窗口与影响系数
- 商品类型金额区间与概率
- 导出目录与编码

### 11.1 命令行参数

可用参数：

- `--config`：指定配置文件路径
- `--init-config`：生成一份默认配置文件
- `--seed`：随机种子
- `--output-dir`：输出目录
- `--obs-start`：观察期开始日期
- `--obs-end`：观察期结束日期
- `--user-reg-end`：注册截止日期
- `--n-users`：生成用户数量

示例：

```powershell
python .\data_generator.py --config .\generator_config.json
```

用命令行覆盖部分配置：

```powershell
python .\data_generator.py --config .\generator_config.json --n-users 5000 --output-dir .\data_large
```

初始化一份新的默认配置：

```powershell
python .\data_generator.py --init-config --config .\my_config.json
```

### 11.2 最常改的配置项

你最常会改的是这些字段：

- `population.n_users`
- `observation.start`
- `observation.end`
- `observation.user_registration_end`
- `sampling_probs.personas`
- `sampling_probs.channels`
- `channel_effects`
- `country_effects`
- `persona_params`
- `special_events`

例如，把用户数改成 `5000`：

```json
{
  "population": {
    "n_users": 5000
  }
}
```

例如，把广告渠道占比提高到 `60%`：

```json
{
  "sampling_probs": {
    "channels": {
      "organic": 0.20,
      "ads": 0.60,
      "referral": 0.10,
      "influencer": 0.10
    }
  }
}
```


## 12. 当前模型的特点与局限

这个生成器的优点是结构清晰、易调参、业务解释性强，但也有一些局限：

- 用户画像一旦生成后不会动态变化
- 没有真实的漏斗链路，例如登录后再玩、玩后再升级的严格因果
- 支付更多是“行为强度驱动”，还没有商品偏好、生命周期阶段等更细粒度逻辑
- 会话时长的波动固定为正态分布，长尾不够真实
- 活动计划表 `campaigns.csv` 目前只是背景数据，不直接驱动生成

如果后续要增强真实性，优先建议扩展这几类能力：

- 生命周期阶段
- 连续留存逻辑
- 更细的事件漏斗
- 商品与画像的绑定关系
- 活动直接影响用户分群和触达


## 13. 最建议优先改的地方

如果你准备把这个生成器继续产品化，建议优先改 4 处：

1. 把画像参数、国家参数、渠道参数、活动参数拆到独立配置文件
2. 把 `campaigns.csv` 和 `SPECIAL_EVENTS` 打通，避免一份活动“只导出不生效”
3. 给事件增加更明确的漏斗关系
4. 增加校验指标，比如 D1、D7、付费率、ARPPU、ARPU 自动输出


## 14. 一句话总结

这个生成器本质上是一个“以画像为底座、以渠道/国家/活动为修正器、以行为驱动付费”的模拟器。  
如果你要调结果，优先记住这条规律：

- 想改 DAU，看活跃率和留存系数
- 想改事件量，看单日事件数和活动倍数
- 想改付费率，看基础付费率和活跃到付费的映射
- 想改收入，看金额档位和国家金额系数
