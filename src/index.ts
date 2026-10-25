import { DurableObject } from "cloudflare:workers";

interface Env {
  BACKEND: DurableObjectNamespace<Backend>;
  APP_ENV: string;
  DATABASE_URL: string;
  GENERATED_DIR: string;
  PAYPAL_MODE: string;
  PAYPAL_API_BASE_URL: string;
  PAYPAL_RETURN_URL: string;
  PAYPAL_CANCEL_URL: string;
  LLM_PROVIDER: string;
  LLM_MODEL: string;
  LLM_BASE_URL: string;
  LLM_API_KEY?: string;
  PAYPAL_CLIENT_ID?: string;
  PAYPAL_CLIENT_SECRET?: string;
  SETTINGS_ADMIN_TOKEN?: string;
  SETTINGS_ENCRYPTION_KEY?: string;
}

const PORT = 8080;
const INACTIVITY_TIMEOUT_MS = 2 * 60 * 60 * 1000;

export class Backend extends DurableObject<Env> {
  private starting: Promise<void> | undefined;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    if (ctx.container!.running) {
      void ctx.blockConcurrencyWhile(() =>
        ctx.container!.setInactivityTimeout(INACTIVITY_TIMEOUT_MS),
      );
    }
  }

  async fetch(request: Request): Promise<Response> {
    this.starting ??= this.startAndWaitForPort().finally(() => {
      this.starting = undefined;
    });
    await this.starting;

    const url = new URL(request.url);
    url.protocol = "http:";
    url.host = "container";
    const forwarded = new Request(url, request);
    forwarded.headers.delete("host");
    return this.ctx.container!.getTcpPort(PORT).fetch(forwarded);
  }

  private async startAndWaitForPort(): Promise<void> {
    const container = this.ctx.container!;
    if (!container.running) {
      container.start({
        image: container.images.base,
        instance: "lite",
        enableInternet: true,
        env: {
          APP_ENV: this.env.APP_ENV,
          DATABASE_URL: this.env.DATABASE_URL,
          GENERATED_DIR: this.env.GENERATED_DIR,
          PAYPAL_MODE: this.env.PAYPAL_MODE,
          PAYPAL_API_BASE_URL: this.env.PAYPAL_API_BASE_URL,
          PAYPAL_RETURN_URL: this.env.PAYPAL_RETURN_URL,
          PAYPAL_CANCEL_URL: this.env.PAYPAL_CANCEL_URL,
          LLM_PROVIDER: this.env.LLM_PROVIDER,
          LLM_MODEL: this.env.LLM_MODEL,
          LLM_BASE_URL: this.env.LLM_BASE_URL,
          ...(this.env.LLM_API_KEY ? { LLM_API_KEY: this.env.LLM_API_KEY } : {}),
          ...(this.env.PAYPAL_CLIENT_ID
            ? { PAYPAL_CLIENT_ID: this.env.PAYPAL_CLIENT_ID }
            : {}),
          ...(this.env.PAYPAL_CLIENT_SECRET
            ? { PAYPAL_CLIENT_SECRET: this.env.PAYPAL_CLIENT_SECRET }
            : {}),
          ...(this.env.SETTINGS_ADMIN_TOKEN
            ? { SETTINGS_ADMIN_TOKEN: this.env.SETTINGS_ADMIN_TOKEN }
            : {}),
          ...(this.env.SETTINGS_ENCRYPTION_KEY
            ? { SETTINGS_ENCRYPTION_KEY: this.env.SETTINGS_ENCRYPTION_KEY }
            : {}),
        },
      });
    }
    await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);

    const port = container.getTcpPort(PORT);
    let lastError: unknown;
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        const response = await port.fetch("http://container/health", {
          signal: AbortSignal.timeout(1000),
        });
        await response.body?.cancel();
        if (!response.ok) {
          throw new Error(`Health check returned ${response.status}`);
        }
        return;
      } catch (error) {
        lastError = error;
        await scheduler.wait(200);
      }
    }
    throw new Error(`Container did not become ready on port ${PORT}`, {
      cause: lastError,
    });
  }
}

export default {
  fetch(request: Request, env: Env): Promise<Response> {
    return env.BACKEND.getByName("primary").fetch(request);
  },
} satisfies ExportedHandler<Env>;
