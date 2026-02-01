import { apiClient, ApiResponse } from './client';

export interface FormulaData {
  formula: string;
  elements: {
    [key: string]: {
      name: string;
      description: string;
      exploration_step?: string;
    };
  };
  explanation: string;
}

export interface FlowchartData {
  steps: Array<{
    id: string;
    name: string;
    description: string;
    order: number;
  }>;
  current_step: string;
}

export const formulaApi = {
  getFormula: async (): Promise<ApiResponse<FormulaData>> => {
    return apiClient.get('/formula');
  },

  getFlowchart: async (): Promise<ApiResponse<FlowchartData>> => {
    return apiClient.get('/formula/flowchart');
  },
};
