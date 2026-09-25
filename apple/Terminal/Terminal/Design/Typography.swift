import SwiftUI

/// The PostScript names of the four bundled faces. The files are in
/// Resources/Fonts and are registered through UIAppFonts in Config/Info.plist.
nonisolated enum FontName {
    static let interRegular = "Inter-Regular"
    static let interSemiBold = "Inter-SemiBold"
    static let monoRegular = "JetBrainsMono-Regular"
    static let monoBold = "JetBrainsMono-Bold"

    static let all = [interRegular, interSemiBold, monoRegular, monoBold]
}

/// The type scale. JetBrains Mono for machine data (codes, times, numbers),
/// Inter for human words. Each style is tied to a system text style, so it grows
/// and shrinks with the phone's text size setting.
nonisolated enum TextStyle: CaseIterable, Sendable {
    /// The flight card's big flight number.
    case heroNumber
    /// Screen titles.
    case title
    /// Empty-state lines.
    case emptyTitle
    /// Sheet and section headers.
    case headline
    /// Buttons and sentences.
    case body
    /// Clocks and times.
    case value
    /// The ">_" mark.
    case mark
    /// Flight numbers in rows.
    case code
    /// Routes in rows.
    case data
    /// Status lines.
    case meta
    /// Row dates.
    case metaBold
    /// Section headings, set in capitals.
    case label
    /// Small notes.
    case caption

    var fontName: String {
        switch self {
        case .heroNumber, .mark, .code, .metaBold: FontName.monoBold
        case .value, .data, .meta: FontName.monoRegular
        case .title, .headline, .label: FontName.interSemiBold
        case .emptyTitle, .body, .caption: FontName.interRegular
        }
    }

    /// The size at the default text size setting.
    var size: CGFloat {
        switch self {
        case .heroNumber: 32
        case .title, .emptyTitle: 24
        case .headline: 17
        case .body, .value, .mark: 15
        case .code, .data: 13
        case .meta, .metaBold, .label, .caption: 11
        }
    }

    /// The system style whose scaling curve this style follows.
    var scalesWith: Font.TextStyle {
        switch self {
        case .heroNumber: .largeTitle
        case .title, .emptyTitle: .title
        case .headline: .headline
        case .body, .value, .mark: .subheadline
        case .code, .data: .footnote
        case .meta, .metaBold, .label, .caption: .caption2
        }
    }

    var tracking: CGFloat {
        switch self {
        case .heroNumber, .label: 1
        default: 0
        }
    }

    var isUppercased: Bool { self == .label }

    /// Extra space between lines. Only the multi-line 24pt text gets any, which
    /// takes Inter's natural 29pt line to 32.
    var extraLineSpacing: CGFloat { self == .emptyTitle ? 3 : 0 }

    var font: Font {
        .custom(fontName, size: size, relativeTo: scalesWith)
    }
}

private struct TextStyleModifier: ViewModifier {
    let style: TextStyle

    func body(content: Content) -> some View {
        content
            .font(style.font)
            .tracking(style.tracking)
            .textCase(style.isUppercased ? .uppercase : nil)
            .lineSpacing(style.extraLineSpacing)
    }
}

extension View {
    /// Sets the font, tracking, case and line spacing of one named style.
    func textStyle(_ style: TextStyle) -> some View {
        modifier(TextStyleModifier(style: style))
    }
}
