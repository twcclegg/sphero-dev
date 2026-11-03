import Foundation

/// Splits Claude's plain-text replies so fenced code blocks (```python ... ```)
/// render as highlighted code instead of as text.
public enum Markdown {
    public static func split(_ text: String) -> [Part] {
        var parts: [Part] = []
        var prose: [Substring] = []
        var code: [Substring] = []
        var language: String?

        func flushProse() {
            let t = prose.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
            if !t.isEmpty { parts.append(.text(t)) }
            prose = []
        }
        for line in text.split(separator: "\n", omittingEmptySubsequences: false) {
            let trimmed = line.drop(while: { $0 == " " })
            if trimmed.hasPrefix("```") {
                if let lang = language {
                    parts.append(.code(CodePart(language: lang, code: code.joined(separator: "\n"))))
                    code = []
                    language = nil
                } else {
                    flushProse()
                    let tag = trimmed.dropFirst(3).trimmingCharacters(in: .whitespaces).lowercased()
                    language = tag.isEmpty || tag == "py" ? "python" : tag
                }
            } else if language != nil {
                code.append(line)
            } else {
                prose.append(line)
            }
        }
        if let lang = language {  // unclosed fence: still show it as code
            parts.append(.code(CodePart(language: lang, code: code.joined(separator: "\n"))))
        }
        flushProse()
        return parts
    }
}
