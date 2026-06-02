Feature: 价值观探索流程

  @id:l3_bdd_values_no_repeat
  Scenario: 模糊回答后，不应重复同一问题
    Given 我使用测试账号 "qa_values_01" 登录系统
    And 我已进入 "values" 页面
    When 我输入 "我更喜欢有影响力的工作"
    And 我点击发送
    Then 我应该看到助手继续追问细节
    And 在后续 3 轮内，不应出现“完全同一句问题重复两次”
    And 当前阶段应保持在 "values" 或进入下一步
