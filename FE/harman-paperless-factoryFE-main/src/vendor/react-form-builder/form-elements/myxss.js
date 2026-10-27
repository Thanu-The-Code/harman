import xss from 'xss';

const myxss = new xss.FilterXSS({
  whiteList: {
    a: ['href', 'title', 'target'],
    u: [],
    br: [],
    b: [],
    i: [],
    ol: ['style'],
    ul: ['style'],
    li: [],
    p: ['style'],
    sub: [],
    sup: [],
    div: ['style'],
    em: [],
    strong: [],
    span: ['style'],
    ins: [],
    // what the designer's text toolbar produces
    s: [],
    strike: [],
    code: [],
    pre: [],
    blockquote: ['style'],
    h1: ['style'],
    h2: ['style'],
    h3: ['style'],
    h4: ['style'],
    hr: [],
  },
});

export default myxss;
