"""Conservative shell command analysis for the guard engine (ADR-0014, ADR-0017).

Stdlib-only (ADR-0012). The analyser never executes anything. It reads a command string as bash,
as PowerShell (backtick escapes removed), and as cmd (caret escapes removed), and reports the union
of what it finds: argv lists, git invocations, candidate paths, nested command texts, and problems
(reasons the command can't be understood, which the engine turns into `ask`).
"""

from __future__ import annotations

import base64
import binascii
import posixpath
import re
import shlex
from dataclasses import dataclass

MAX_DEPTH = 5

_SEPARATORS = frozenset(";|&\n\r(){}")
_WORD_END = frozenset(" \t;|&<>()\n\r")
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_EXE_SUFFIX = re.compile(r"\.(exe|cmd|bat|com)$")

_WRAPPERS = frozenset(
    {"sudo", "doas", "env", "nohup", "time", "timeout", "nice", "ionice", "stdbuf", "xargs"}
    | {"command", "exec", "builtin", "chronic", "caffeinate", "&"}
)
_WRAPPER_OPTS_WITH_VALUE = {
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}),
    "nice": frozenset({"-n"}),
    "ionice": frozenset({"-c", "-n"}),
    "xargs": frozenset({"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"}),
    "env": frozenset({"-u", "-C"}),
    "timeout": frozenset({"-s", "-k"}),
}
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish", "ash", "busybox"})
_POWERSHELLS = frozenset({"powershell", "pwsh"})
_PS_OPTS_WITH_VALUE = frozenset(
    {"-executionpolicy", "-ex", "-ep", "-windowstyle", "-w", "-outputformat", "-o"}
    | {"-inputformat", "-if", "-workingdirectory", "-wd", "-configurationname", "-settingsfile"}
)
_EVALUATORS = frozenset({"eval", "iex", "invoke-expression"})
_START_PROCESS = frozenset({"start-process", "saps", "start"})
_INTERPRETERS = frozenset(
    {"python", "python3", "py", "node", "perl", "ruby", "php", "deno", "bun", "pypy", "pypy3"}
)
_CODE_FLAGS = frozenset({"-c", "-e", "-E", "-r", "--eval", "--command"})

_GIT_OPTS_WITH_VALUE = frozenset(
    {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
)
_DANGEROUS_GIT_CONFIG = re.compile(r"^(alias\.|core\.hookspath$|core\.sshcommand$)", re.I)
_GIT_LIKE = frozenset({"git", "hub"})  # hub wraps git (ADR-0018)
_HEURISTIC_GIT = re.compile(r"(?i)(?<![\w.\-])(git|gh|glab|hub)(?:\.exe)?(?![\w.\-])")
_HEURISTIC_STRIP = "'\"()`,;{}"


@dataclass(frozen=True, slots=True)
class GitCall:
    subcommand: str | None
    args: tuple[str, ...] = ()
    config: tuple[str, ...] = ()

    def text(self) -> str:
        return " ".join(x for x in (self.subcommand or "", *self.args) if x)


@dataclass(frozen=True, slots=True)
class ShellAnalysis:
    command: str
    argvs: tuple[tuple[str, ...], ...]
    git_calls: tuple[GitCall, ...]
    paths: tuple[str, ...]
    texts: tuple[str, ...]  # original + nested/decoded command texts, for regex selectors
    problems: tuple[str, ...]
    simple: bool  # one segment, no redirects, no nesting, parseable

    @property
    def parseable(self) -> bool:
        return not self.problems


def command_base(token: str) -> str:
    """Lower-cased basename without .exe etc.: '/usr/bin/git', 'C:\\Git\\GIT.EXE' -> 'git'."""
    base = token.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return _EXE_SUFFIX.sub("", base)


def _read_word(text: str, i: int) -> tuple[str, int]:
    n = len(text)
    if i < n and text[i] in "'\"":
        quote = text[i]
        j = text.find(quote, i + 1)
        if j == -1:
            return text[i + 1 :], n
        return text[i + 1 : j], j + 1
    j = i
    while j < n and text[j] not in _WORD_END:
        j += 1
    return text[i:j], j


def _split(text: str) -> tuple[list[str], list[str], list[str]] | None:
    """Quote-aware split -> (segments, redirect targets, substitutions); None if unbalanced."""
    segments: list[str] = []
    redirects: list[str] = []
    substitutions: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    depth = 0
    sub_start = 0
    i, n = 0, len(text)

    def flush() -> None:
        segment = "".join(buf).strip()
        if segment:
            segments.append(segment)
        buf.clear()

    while i < n:
        c = text[i]
        if quote:
            buf.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                buf.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if depth:
            if c in "'\"":
                # quotes inside $( ... ): skip the quoted run so ')' inside it isn't counted
                j = text.find(c, i + 1)
                j = n - 1 if j == -1 else j
                buf.append(text[i : j + 1])
                i = j + 1
                continue
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    substitutions.append(text[sub_start:i])
            buf.append(c)
            i += 1
            continue
        if c in "'\"":
            quote = c
            buf.append(c)
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            buf.append(text[i : i + 2])
            i += 2
            continue
        if c in "$<>" and text[i + 1 : i + 2] == "(":
            depth = 1
            sub_start = i + 2
            buf.append(text[i : i + 2])
            i += 2
            continue
        if c == "`":
            j = text.find("`", i + 1)
            if j != -1:
                substitutions.append(text[i + 1 : j])
                buf.append(text[i : j + 1])
                i = j + 1
                continue
        if c == ">":
            j = i + 1
            if j < n and text[j] in ">|":
                j += 1
            if j < n and text[j] == "&":  # fd duplication: 2>&1
                j += 1
                while j < n and text[j].isdigit():
                    j += 1
                buf.append(" ")
                i = j
                continue
            while j < n and text[j] in " \t":
                j += 1
            target, j = _read_word(text, j)
            if target:
                redirects.append(target)
            buf.append(" ")
            i = j
            continue
        if c in _SEPARATORS:
            flush()
            i += 1
            continue
        buf.append(c)
        i += 1
    if quote:
        return None
    if depth:  # unterminated $( ... ): analyse what we have
        substitutions.append(text[sub_start:])
    flush()
    return segments, redirects, substitutions


def _tokenize(segment: str) -> list[list[str]]:
    """Tokenise with bash escapes and with literal backslashes (Windows paths). Distinct results."""
    results: list[list[str]] = []
    for escape in ("\\", ""):
        try:
            lexer = shlex.shlex(segment, posix=True)
            lexer.whitespace_split = True
            lexer.escape = escape
            tokens = list(lexer)
        except ValueError:
            continue
        if tokens and tokens not in results:
            results.append(tokens)
    return results


class _Analyzer:
    def __init__(self, command: str) -> None:
        self.command = command
        self.argvs: list[tuple[str, ...]] = []
        self.git_calls: list[GitCall] = []
        self.paths: list[str] = []
        self.texts: list[str] = []
        self.problems: list[str] = []
        self.record_problems = True
        self.nested = False
        self.top_segments = 0
        self.top_redirects = 0

    def problem(self, reason: str) -> None:
        if self.record_problems and reason not in self.problems:
            self.problems.append(reason)

    # ------------------------------------------------------------------ commands

    def run(self, text: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            self.problem(f"nesting deeper than {MAX_DEPTH}")
            self.heuristic_git(text)
            return
        if depth:
            self.nested = True
        if text not in self.texts:
            self.texts.append(text)
        split = _split(text)
        if split is None:
            self.problem("unbalanced quotes")
            self.heuristic_git(text)
            return
        segments, redirects, substitutions = split
        if depth == 0 and self.record_problems:
            self.top_segments = len(segments)
            self.top_redirects = len(redirects)
        for target in redirects:
            self.add_path(target)
        for inner in substitutions:
            self.run(inner, depth + 1)
        for segment in segments:
            token_sets = _tokenize(segment)
            if not token_sets:
                self.problem(f"cannot tokenize: {segment[:60]}")
                self.heuristic_git(segment)
                continue
            for argv in token_sets:
                self.argv(argv, depth)

    def argv(self, argv: list[str], depth: int) -> None:
        argv = list(argv)
        while argv:
            head = argv[0]
            base = command_base(head)
            if _ASSIGNMENT.match(head):
                argv.pop(0)
                continue
            if base in _WRAPPERS:
                argv.pop(0)
                with_value = _WRAPPER_OPTS_WITH_VALUE.get(base, frozenset())
                while argv and argv[0].startswith("-") and argv[0] != "-":
                    opt = argv.pop(0)
                    if opt in with_value and argv:
                        argv.pop(0)
                if base == "timeout" and argv and argv[0][:1].isdigit():
                    argv.pop(0)
                continue
            break
        if not argv:
            return
        self.argvs.append(tuple(argv))
        head, args = argv[0], argv[1:]
        base = command_base(head)
        for arg in args:
            if arg.startswith("-"):
                if "=" in arg:
                    self.add_path(arg.split("=", 1)[1])
                continue
            self.add_path(arg)

        if head.startswith("$") or "$(" in head or "${" in head or "`" in head:
            self.problem(f"dynamic command name {head!r}")
            self.heuristic_git(" ".join(argv))
            return
        if base in _GIT_LIKE:
            self.git(args)
        elif base in _SHELLS:
            self.shell_c(args, depth)
        elif base == "cmd":
            self.cmd_c(args, depth)
        elif base in _POWERSHELLS:
            self.powershell(args, depth)
        elif base in _EVALUATORS:
            rest = [a for a in args if a.lower() != "-command"]
            if rest:
                self.run(" ".join(rest), depth + 1)
        elif base in _START_PROCESS:
            self.start_process(args, depth)
        elif base in _INTERPRETERS:
            self.interpreter(args)

    def shell_c(self, args: list[str], depth: int) -> None:
        for idx, arg in enumerate(args):
            if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", arg) and idx + 1 < len(args):
                self.run(args[idx + 1], depth + 1)
                return

    def cmd_c(self, args: list[str], depth: int) -> None:
        for idx, arg in enumerate(args):
            low = arg.lower()
            if low in ("/c", "/k", "/r"):
                self.run(" ".join(args[idx + 1 :]), depth + 1)
                return
            if low[:2] in ("/c", "/k") and len(arg) > 2:  # /c"git push"
                self.run(" ".join([arg[2:], *args[idx + 1 :]]), depth + 1)
                return

    def powershell(self, args: list[str], depth: int) -> None:
        idx = 0
        while idx < len(args):
            arg = args[idx]
            low = arg.lower()
            # -EncodedCommand: aliases -e/-ec, or any unambiguous prefix from -en
            if low in ("-e", "-ec") or (len(low) >= 3 and "-encodedcommand".startswith(low)):
                if idx + 1 < len(args):
                    self.encoded(args[idx + 1], depth)
                return
            if low.startswith("-c") and "-command".startswith(low):
                if idx + 1 < len(args):
                    self.run(" ".join(args[idx + 1 :]), depth + 1)
                return
            if low in ("-file", "-f"):
                return
            if low in _PS_OPTS_WITH_VALUE:
                idx += 2
                continue
            if low.startswith("-"):
                idx += 1
                continue
            # positional: powershell.exe treats it as -Command text
            if not low.endswith(".ps1"):
                self.run(" ".join(args[idx:]), depth + 1)
            return

    def encoded(self, value: str, depth: int) -> None:
        try:
            decoded = base64.b64decode(value, validate=True).decode("utf-16-le")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            self.problem("undecodable -EncodedCommand")
            return
        self.run(decoded, depth + 1)

    def start_process(self, args: list[str], depth: int) -> None:
        names = {"-filepath", "-argumentlist", "-args", "-wait", "-nonewwindow", "-passthru"}
        rest = [a.replace(",", " ") for a in args if a.lower() not in names]
        if rest:
            self.run(" ".join(rest), depth + 1)

    def interpreter(self, args: list[str]) -> None:
        for idx, arg in enumerate(args):
            if arg in _CODE_FLAGS and idx + 1 < len(args):
                code = args[idx + 1]
                self.nested = True
                if code not in self.texts:
                    self.texts.append(code)
                self.heuristic_git(code)
                return

    # ------------------------------------------------------------------ git

    def git(self, args: list[str] | tuple[str, ...]) -> None:
        config: list[str] = []
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in _GIT_OPTS_WITH_VALUE:
                value = args[i + 1] if i + 1 < len(args) else ""
                if arg in ("-c", "--config-env"):
                    config.append(value)
                i += 2
                continue
            if arg.startswith("--") and "=" in arg:
                if arg.startswith("--config-env="):
                    config.append(arg.split("=", 1)[1])
                i += 1
                continue
            if arg.startswith("-"):
                i += 1
                continue
            break
        subcommand = args[i].lower() if i < len(args) else None
        for entry in config:
            if _DANGEROUS_GIT_CONFIG.match(entry.split("=", 1)[0]):
                self.problem(f"git config override {entry.split('=', 1)[0]!r}")
        call = GitCall(subcommand, tuple(args[i + 1 :]), tuple(config))
        if call not in self.git_calls:
            self.git_calls.append(call)

    def heuristic_git(self, text: str) -> None:
        """Best-effort git/gh/glab/hub detection in unparseable text (interpreter code etc.)."""
        for match in _HEURISTIC_GIT.finditer(text):
            rest = text[match.end() :]
            first_cmd = re.split(r"[;&|\n]", rest, maxsplit=1)[0]
            tokens = [t.strip(_HEURISTIC_STRIP) for t in re.split(r"[\s,\[\]]+", first_cmd)]
            tokens = [t for t in tokens if t]
            base = match.group(1).lower()
            if base in _GIT_LIKE:
                self.git(tokens)
            argv = (base, *tokens)
            if argv not in self.argvs:
                self.argvs.append(argv)

    # ------------------------------------------------------------------ paths

    def add_path(self, token: str) -> None:
        token = token.strip().strip("'\"")
        if not token or token in self.paths:
            return
        self.paths.append(token)

    def result(self) -> ShellAnalysis:
        simple = (
            not self.problems
            and not self.nested
            and self.top_segments == 1
            and self.top_redirects == 0
        )
        return ShellAnalysis(
            command=self.command,
            argvs=tuple(dict.fromkeys(self.argvs)),
            git_calls=tuple(self.git_calls),
            paths=tuple(self.paths),
            texts=tuple(self.texts),
            problems=tuple(self.problems),
            simple=simple,
        )


def _readings(command: str) -> list[str]:
    readings = [command]
    if "`" in command:
        readings.append(re.sub(r"`(.)", r"\1", command, flags=re.DOTALL))  # PowerShell escapes
    if "^" in command:
        readings.append(re.sub(r"\^(.)", r"\1", command, flags=re.DOTALL))  # cmd escapes
    return list(dict.fromkeys(readings))


def analyze(command: str) -> ShellAnalysis:
    analyzer = _Analyzer(command)
    if not command.strip():
        analyzer.problem("empty command")
        return analyzer.result()
    for index, reading in enumerate(_readings(command)):
        # Problems only count for the as-written reading; other readings only add findings.
        analyzer.record_problems = index == 0
        analyzer.run(reading, 0)
    analyzer.record_problems = True
    return analyzer.result()


def normalize_path(path: str, root: str | None = None) -> str:
    """Slash-normalised, root-relative, with ./ and .. collapsed (ADR-0017)."""
    p = path.strip().strip("'\"").replace("\\", "/")
    if root:
        r = root.replace("\\", "/").rstrip("/")
        if r and p.lower().startswith(r.lower() + "/"):
            p = p[len(r) + 1 :]
        elif p.lower() == r.lower():
            p = "."
    if not p:
        return p
    normalized = posixpath.normpath(p)
    return "." if normalized in ("", ".") else normalized
