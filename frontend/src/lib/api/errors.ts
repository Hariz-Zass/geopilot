export type ApiErrorPayload = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(args: {
    message: string;
    status: number;
    code?: string;
    requestId?: string;
  }) {
    super(args.message);
    this.name = "ApiError";
    this.status = args.status;
    this.code = args.code ?? "api_error";
    this.requestId = args.requestId;
  }
}
