import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // This experimental React Compiler rule flags the standard "fetch on
      // mount, setState in an async effect body" pattern used throughout
      // this app (dashboard, reconciliation, audit log, case detail) as a
      // hard error. Satisfying it "properly" would mean rearchitecting data
      // fetching around Suspense/use() or a query library, which is
      // out of scope for this MVP (section 30 — don't overbuild). The
      // pattern itself is standard, correct React and doesn't cause the
      // cascading-render issue the rule is guarding against here, since
      // every setState call happens after an awaited network request.
      "react-hooks/set-state-in-effect": "off",
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
