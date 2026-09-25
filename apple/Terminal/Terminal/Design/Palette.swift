import SwiftUI

/// One colour as exact sRGB components (0 to 255) and an alpha (0 to 1).
///
/// Kept as numbers rather than as a `Color` so the contrast tests compute with
/// the same values the screen draws with.
nonisolated struct RGBA: Equatable, Sendable {
    let red: Double
    let green: Double
    let blue: Double
    let alpha: Double

    init(_ red: Double, _ green: Double, _ blue: Double, alpha: Double = 1) {
        self.red = red
        self.green = green
        self.blue = blue
        self.alpha = alpha
    }

    init(hex: UInt32, alpha: Double = 1) {
        self.init(
            Double((hex >> 16) & 0xFF),
            Double((hex >> 8) & 0xFF),
            Double(hex & 0xFF),
            alpha: alpha
        )
    }

    var color: Color {
        Color(.sRGB, red: red / 255, green: green / 255, blue: blue / 255, opacity: alpha)
    }
}

/// Every colour the app paints, from the React Native app's tokens
/// (android/lib/cards.ts, lib/glass.tsx, lib/flightstatus.tsx), with the page
/// moved to #050505.
nonisolated enum Palette {
    // The page, and what sits on it.
    static let page = RGBA(hex: 0x050505)
    /// Cards and rows on the page.
    static let surface1 = RGBA(255, 255, 255, alpha: 0.045)
    /// A control inside a card: a pill, a picker.
    static let surface2 = RGBA(255, 255, 255, alpha: 0.08)
    /// The rule under a sheet heading.
    static let hairline = RGBA(255, 255, 255, alpha: 0.07)
    /// The 1pt edge of a glass surface.
    static let glassEdge = RGBA(255, 255, 255, alpha: 0.08)
    /// The backdrop behind sheets and glass.
    static let scrim = RGBA(0, 0, 0, alpha: 0.40)

    /// Live or actionable things, and the ">_" mark. Nothing else is green.
    static let green = RGBA(hex: 0x4ADE80)
    /// Late or at risk.
    static let amber = RGBA(hex: 0xFBBF24)
    /// Cancelled.
    static let red = RGBA(hex: 0xF87171)

    /// Opaque card surfaces for a disrupted flight.
    static let cancelledSurface = RGBA(41, 23, 23)
    static let divertedSurface = RGBA(41, 34, 13)

    /// The one ink every text grey is drawn from. At full strength it is the
    /// text white: bright enough for 15:1 on the page without the glow pure
    /// white has on a near-black OLED screen.
    static let ink = RGBA(226, 226, 226)
}

/// The text scale: four strengths of the one ink, replacing the fifteen alphas
/// the React Native app used. Every level passes WCAG AA (4.5:1) for small text
/// on the page and on a card; the old 0.4 level did not, so it is gone.
nonisolated enum Ink: CaseIterable, Sendable {
    /// Text white: values, titles, flight numbers.
    case primary
    /// Chevrons, the "scheduled" status word.
    case secondary
    /// Routes, dates, the "landed" status word, empty-state lines.
    case tertiary
    /// Section labels, ages, early figures, the phone's own time.
    case quaternary

    var alpha: Double {
        switch self {
        case .primary: 1.0
        case .secondary: 0.75
        case .tertiary: 0.6
        case .quaternary: 0.52
        }
    }

    var rgba: RGBA {
        RGBA(Palette.ink.red, Palette.ink.green, Palette.ink.blue, alpha: alpha)
    }

    var color: Color { rgba.color }
}
