// Type shared by the dashboard and the generic workspace.
// This mirrors backend/tool_registry.py's `to_public_dict` shape exactly, so
// a new tool that only adds a registry entry needs no frontend changes here.
export interface ToolParameter {
  name: string;
  label: string;
  default: number;
  minimum: number | null;
  maximum: number | null;
  step: number;
}

export interface Tool {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  accepted_extensions: string[];
  parameters: ToolParameter[];
}
