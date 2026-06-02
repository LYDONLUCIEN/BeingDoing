Feature: Rumination 引导顺序

  @id:l3_bdd_rumination_guidance
  Scenario: 编辑假设后失焦，应出现正确引导
    Given 我已进入 "rumination" 阶段
    And 当前有可编辑的假设表格
    When 我把第 1 行假设修改为 "我想做独立咨询"
    And 我点击表格外空白区域
    Then 右侧应出现引导语 "是否填写好了"
    When 我回复 "确认，可以继续"
    Then 当前阶段应保持在 "rumination" 或进入下一步
