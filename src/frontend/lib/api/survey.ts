/**
 * 调研问卷 API
 * 支持 simple（激活码）和 complex（session）两种模式
 */

import { apiClient, ApiResponse } from './client';
import type { SurveyData } from '@/lib/survey/schema';

/** 每个 phase 允许上传/保存的上一轮咨询结果 */
export const priorContextApi = {
  /** 获取上一轮咨询结果（激活码模式） */
  getForActivation: async (
    activationCode: string,
    phase: string
  ): Promise<ApiResponse<{ context_text: string }>> => {
    return apiClient.get('/simple-chat/prior-context', {
      params: { activation_code: activationCode, phase },
    });
  },

  /** 保存/上传上一轮咨询结果（激活码模式） */
  saveForActivation: async (
    activationCode: string,
    phase: string,
    contextText: string
  ): Promise<ApiResponse<void>> => {
    return apiClient.post('/simple-chat/prior-context', {
      activation_code: activationCode,
      phase,
      context_text: contextText,
    });
  },
};

/** Simple 模式：根据激活码保存调研 */
export const surveyApi = {
  /** 保存调研（激活码模式） */
  saveForActivation: async (
    activationCode: string,
    surveyData: SurveyData
  ): Promise<ApiResponse<void>> => {
    return apiClient.post('/simple-chat/survey', {
      activation_code: activationCode,
      survey_data: surveyData,
    });
  },

  /** 获取调研（激活码模式） */
  getForActivation: async (
    activationCode: string
  ): Promise<ApiResponse<{ survey_data: SurveyData }>> => {
    return apiClient.get('/simple-chat/survey', {
      params: { activation_code: activationCode },
    });
  },

  /** 保存调研（Session 模式，需登录） */
  saveForSession: async (
    sessionId: string,
    surveyData: SurveyData
  ): Promise<ApiResponse<void>> => {
    return apiClient.post(`/sessions/${sessionId}/survey`, {
      survey_data: surveyData,
    });
  },

  /** 获取调研（Session 模式） */
  getForSession: async (
    sessionId: string
  ): Promise<ApiResponse<{ survey_data: SurveyData }>> => {
    return apiClient.get(`/sessions/${sessionId}/survey`);
  },
};
