// The builder's HTML sanitiser (myxss.js): the tags its text elements may contain.
declare const myxss: { process(html: string): string };
export default myxss;
