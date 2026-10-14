/** Keep automatic data collection disabled when upgrading the browser SDK. */
export function sentryPrivacyOptions() {
  return {
    // Sentry v11 defaults to collecting these categories unless explicitly disabled.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
      graphQL: { document: false, variables: false },
      genAI: { inputs: false, outputs: false },
      databaseQueryData: false,
      queues: false,
      stackFrameVariables: false,
      frameContextLines: 0,
    },
    tracesSampleRate: 0,
  };
}
