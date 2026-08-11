import fs from "node:fs";
import katex from "katex";

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const rendered = payload.formulas.map(({ tex, display }) => {
  try {
    return katex.renderToString(tex, {
      displayMode: Boolean(display),
      throwOnError: false,
      strict: "warn",
      output: "htmlAndMathml"
    });
  } catch (error) {
    return `<span class="formula-error">${String(error.message)}</span>`;
  }
});
process.stdout.write(JSON.stringify({ rendered }));
