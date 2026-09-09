import { useQueryClient } from "@tanstack/react-query";

/** Invalidate every cached variant of the named generated API operations. */
export function useRefreshQueries() {
  const queryClient = useQueryClient();
  return (...operations: string[]) =>
    queryClient.invalidateQueries({
      predicate: ({ queryKey }) => {
        const head = queryKey[0];
        return (
          typeof head === "object" &&
          head !== null &&
          "_id" in head &&
          operations.includes(String(head._id))
        );
      },
    });
}
