/**
 * The Lezer external tokenizer: each token is one lexeme of the server's lexer, found by `lex.ts`. The
 * document is read through `InputStream.peek` one code point at a time (UTF-16 surrogate pairs joined), so
 * `lex.ts` sees code points, as `lexer.py` does, and the token's end is converted back to UTF-16 units here.
 */
import { ExternalTokenizer, type InputStream } from "@lezer/lr";
import { isSpace, lexemeAt, type LexemeKind, type Source, type TokenizerVersion } from "./lex";
import * as terms from "./parser.terms";

const TERM: Readonly<Record<LexemeKind, number>> = {
  LPAREN: terms.LParen,
  RPAREN: terms.RParen,
  PIPE: terms.Pipe,
  AND: terms.And,
  OR: terms.Or,
  NOT: terms.Not,
  MINUS: terms.Minus,
  NEAR: terms.Near,
  BAD_NEAR: terms.BadNear,
  FIELD: terms.Field,
  UNKNOWN_FIELD: terms.UnknownField,
  PHRASE: terms.Phrase,
  RANGE: terms.Range,
  WILDCARD: terms.Wildcard,
  WORD: terms.Word,
};

const isHigh = (u: number) => u >= 0xd800 && u < 0xdc00;
const isLow = (u: number) => u >= 0xdc00 && u < 0xe000;

/** The stream from its current position, as code points: `at(0)` is the first, `at(-1)` the one before. */
class StreamSource implements Source {
  private readonly cps: string[] = [];
  /** `units[k]`: where code point `k` starts, in UTF-16 units from the stream position. */
  private readonly units: number[] = [0];
  private done = false;

  constructor(
    private readonly input: InputStream,
    readonly tokenizer: TokenizerVersion,
  ) {}

  at(k: number): string | undefined {
    if (k === -1) return this.previous();
    if (k < 0) return undefined;
    while (this.cps.length <= k && !this.done) this.decode();
    return this.cps[k];
  }

  /** The UTF-16 offset from the stream position at which code point `k` starts (`k` ≤ the length). */
  offset(k: number): number {
    this.at(k - 1);
    return this.units[k] ?? this.units[this.units.length - 1] ?? 0;
  }

  private decode(): void {
    const u = this.units[this.cps.length] ?? 0;
    const a = this.input.peek(u);
    if (a < 0) {
      this.done = true;
      return;
    }
    const b = isHigh(a) ? this.input.peek(u + 1) : -1;
    const width = isLow(b) ? 2 : 1;
    this.cps.push(width === 2 ? String.fromCharCode(a, b) : String.fromCharCode(a));
    this.units.push(u + width);
  }

  private previous(): string | undefined {
    const a = this.input.peek(-1);
    if (a < 0) return undefined;
    const b = isLow(a) ? this.input.peek(-2) : -1;
    return isHigh(b) ? String.fromCharCode(b, a) : String.fromCharCode(a);
  }
}

function queryTokensFor(tokenizer: TokenizerVersion): ExternalTokenizer {
  return new ExternalTokenizer((input) => {
    if (input.next < 0) return;
    const q = new StreamSource(input, tokenizer);
    if (isSpace(q.at(0))) {
      let k = 1;
      while (isSpace(q.at(k))) k++;
      input.acceptToken(terms.space, q.offset(k));
      return;
    }
    const { kind, end } = lexemeAt(q, 0);
    input.acceptToken(TERM[kind], q.offset(end));
  });
}

export const queryTokens = queryTokensFor("3");
export const queryTokensV2 = queryTokensFor("2");
