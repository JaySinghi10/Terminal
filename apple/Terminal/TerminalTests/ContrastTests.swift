import Foundation
import Testing
@testable import Terminal

// WCAG 2.x contrast, computed here rather than in the app: the app only needs
// the colours, the tests need the arithmetic.
extension RGBA {
    /// This colour painted over an opaque background: what the eye sees.
    func over(_ background: RGBA) -> RGBA {
        RGBA(
            background.red + (red - background.red) * alpha,
            background.green + (green - background.green) * alpha,
            background.blue + (blue - background.blue) * alpha
        )
    }

    /// WCAG relative luminance of an opaque colour.
    var relativeLuminance: Double {
        func linear(_ channel: Double) -> Double {
            let c = channel / 255
            return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    }

    static func contrast(_ a: RGBA, _ b: RGBA) -> Double {
        let (la, lb) = (a.relativeLuminance, b.relativeLuminance)
        return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
    }
}

@Suite("Contrast")
struct ContrastTests {
    /// WCAG AA for text under 18pt.
    static let smallTextMinimum = 4.5
    static let page = Palette.page
    static let card = Palette.surface1.over(Palette.page)

    @Test("The formula gives WCAG's known values")
    func formula() {
        let white = RGBA(255, 255, 255)
        let black = RGBA(0, 0, 0)
        #expect(abs(RGBA.contrast(white, black) - 21) < 0.001)
        #expect(abs(RGBA.contrast(black, black) - 1) < 0.001)
        // #767676 on white is the classic lightest grey that still passes AA.
        #expect(RGBA.contrast(RGBA(hex: 0x767676), white) >= 4.5)
        #expect(RGBA.contrast(RGBA(hex: 0x777777), white) < 4.5)
    }

    @Test("Every grey level reaches 4.5:1 on the page and on a card", arguments: Ink.allCases)
    func inkLevel(_ ink: Ink) {
        let onPage = RGBA.contrast(ink.rgba.over(Self.page), Self.page)
        let onCard = RGBA.contrast(ink.rgba.over(Self.card), Self.card)
        #expect(onPage >= Self.smallTextMinimum, "\(ink) on the page is \(onPage)")
        #expect(onCard >= Self.smallTextMinimum, "\(ink) on a card is \(onCard)")
    }

    @Test("Every status colour reaches 4.5:1 on the page and on a card", arguments: StatusTone.allCases)
    func statusTone(_ tone: StatusTone) {
        let onPage = RGBA.contrast(tone.rgba.over(Self.page), Self.page)
        let onCard = RGBA.contrast(tone.rgba.over(Self.card), Self.card)
        #expect(onPage >= Self.smallTextMinimum, "\(tone) on the page is \(onPage)")
        #expect(onCard >= Self.smallTextMinimum, "\(tone) on a card is \(onCard)")
    }
}
