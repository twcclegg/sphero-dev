/// A small Python tokenizer for colouring code. It only needs to look right,
/// not to be a full lexer: it splits source into runs that join back into the
/// original text exactly.
public enum TokenKind: Equatable, Sendable {
    case plain, keyword, builtin, edu, string, comment, number, definition, decorator
}

public struct Token: Equatable, Sendable {
    public var text: String
    public var kind: TokenKind

    public init(_ text: String, _ kind: TokenKind) {
        self.text = text
        self.kind = kind
    }
}

public enum PythonHighlighter {
    static let keywords: Set<String> = [
        "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class",
        "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global",
        "if", "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise",
        "return", "try", "while", "with", "yield", "match", "case",
    ]
    static let builtins: Set<String> = [
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max",
        "min", "print", "range", "round", "str", "sum", "tuple", "zip", "self",
    ]
    /// The Sphero Edu app's commands (`src/sphero_dev/edu_builtins.pyi`).
    static let edu: Set<String> = [
        "roll", "set_speed", "set_heading", "stop_roll", "spin", "raw_motor",
        "set_stabilization", "reset_aim", "calibrate_compass", "set_compass_direction",
        "set_main_led", "set_back_led", "set_front_led", "get_main_led", "fade", "strobe",
        "set_matrix_pixel", "set_matrix_line", "set_matrix_fill", "set_matrix_character",
        "set_matrix_rotation", "clear_matrix", "scroll_matrix_text", "get_acceleration",
        "get_vertical_acceleration", "get_orientation", "get_gyroscope", "get_velocity",
        "get_location", "get_distance", "get_speed", "get_heading", "get_luminosity",
        "get_compass_direction", "start_ir_broadcast", "stop_ir_broadcast", "start_ir_follow",
        "stop_ir_follow", "start_ir_evade", "stop_ir_evade", "send_ir_message", "delay",
        "speak", "register_event", "exit_program", "start_program",
    ]

    public static func tokenize(_ source: String) -> [Token] {
        let s = Array(source)
        var out: [Token] = []
        var i = 0
        var lastWord = ""

        func emit(_ start: Int, _ end: Int, _ kind: TokenKind) {
            let text = String(s[start..<end])
            if kind == .plain, let last = out.last, last.kind == .plain {
                out[out.count - 1].text += text
            } else {
                out.append(Token(text, kind))
            }
        }
        func isIdentStart(_ c: Character) -> Bool { c == "_" || c.isLetter }
        func isIdent(_ c: Character) -> Bool { c == "_" || c.isLetter || c.isNumber }

        while i < s.count {
            let c = s[i]
            let start = i
            if c == "#" {
                while i < s.count, s[i] != "\n" { i += 1 }
                emit(start, i, .comment)
            } else if let end = stringEnd(s, at: i) {
                i = end
                emit(start, i, .string)
            } else if c.isNumber || (c == "." && i + 1 < s.count && s[i + 1].isNumber) {
                i += 1
                while i < s.count, isIdent(s[i]) || s[i] == "." { i += 1 }
                emit(start, i, .number)
            } else if c == "@" && lineIsBlankBefore(s, i) {
                i += 1
                while i < s.count, isIdent(s[i]) || s[i] == "." { i += 1 }
                emit(start, i, .decorator)
            } else if isIdentStart(c) {
                while i < s.count, isIdent(s[i]) { i += 1 }
                let word = String(s[start..<i])
                let kind: TokenKind
                if lastWord == "def" || lastWord == "class" {
                    kind = .definition
                } else if keywords.contains(word) {
                    kind = .keyword
                } else if edu.contains(word) {
                    kind = .edu
                } else if builtins.contains(word) {
                    kind = .builtin
                } else {
                    kind = .plain
                }
                emit(start, i, kind)
                lastWord = word
                continue
            } else {
                i += 1
                emit(start, i, .plain)
                if !c.isWhitespace { lastWord = "" }
                continue
            }
            lastWord = ""
        }
        return out
    }

    private static func lineIsBlankBefore(_ s: [Character], _ i: Int) -> Bool {
        var j = i - 1
        while j >= 0, s[j] != "\n" {
            if !s[j].isWhitespace { return false }
            j -= 1
        }
        return true
    }

    /// If a string literal (with optional r/b/f/u prefix) starts at `i`, where it ends.
    private static func stringEnd(_ s: [Character], at i: Int) -> Int? {
        var j = i
        while j < s.count, j - i < 2, "rRbBfFuU".contains(s[j]) { j += 1 }
        guard j < s.count, s[j] == "\"" || s[j] == "'" else { return nil }
        // A prefix must not be the tail of a longer identifier (e.g. `bar"`).
        if j > i, i > 0, s[i - 1] == "_" || s[i - 1].isLetter || s[i - 1].isNumber {
            return nil
        }
        let q = s[j]
        let triple = j + 2 < s.count && s[j + 1] == q && s[j + 2] == q
        var k = j + (triple ? 3 : 1)
        while k < s.count {
            if s[k] == "\\" {
                k += 2
                continue
            }
            if triple {
                if s[k] == q, k + 2 < s.count, s[k + 1] == q, s[k + 2] == q { return k + 3 }
            } else {
                if s[k] == q { return k + 1 }
                if s[k] == "\n" { return k }  // unterminated: stop at the line end
            }
            k += 1
        }
        return s.count
    }
}
