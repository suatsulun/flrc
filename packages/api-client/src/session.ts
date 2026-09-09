import { meOptions } from "./generated/@tanstack/react-query.gen";
import { me } from "./generated/sdk.gen";

// A sleeping demo API must not hold the route guard on a spinner indefinitely.
export function sessionOptions() {
  return {
    ...meOptions(),
    retry: false,
    queryFn: async ({ signal }: { signal: AbortSignal }) => {
      const { data } = await me({
        signal: AbortSignal.any([signal, AbortSignal.timeout(5_000)]),
        throwOnError: true,
      });
      return data;
    },
  };
}
