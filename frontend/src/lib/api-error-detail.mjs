/**
 * @param {unknown} issue
 * @returns {string | null}
 */
function formatValidationIssue(issue) {
  if (typeof issue === "string") return issue;
  if (!issue || typeof issue !== "object" || Array.isArray(issue)) return null;

  const message = "msg" in issue && typeof issue.msg === "string"
    ? issue.msg
    : "message" in issue && typeof issue.message === "string"
      ? issue.message
      : null;
  if (message === null) return null;

  const location = Array.isArray(issue.loc)
    ? issue.loc
        .filter((part) => part !== "body")
        .reduce((path, part) => {
          if (typeof part === "number") return `${path}[${part}]`;
          if (typeof part !== "string") return path;
          return path ? `${path}.${part}` : part;
        }, "")
    : "";
  return location ? `${location}: ${message}` : message;
}

/**
 * @param {unknown} detail
 * @returns {string | null}
 */
export function formatApiErrorDetail(detail) {
  if (typeof detail === "string") return detail;
  const issues = Array.isArray(detail) ? detail : [detail];
  const messages = issues
    .map(formatValidationIssue)
    .filter((message) => message !== null);
  return messages.length ? messages.join("; ") : null;
}
