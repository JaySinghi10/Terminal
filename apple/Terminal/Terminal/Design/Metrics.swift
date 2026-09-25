import CoreGraphics

/// Corner radii. Every rounded surface uses Apple's continuous corners
/// (`RoundedRectangle(cornerRadius:style: .continuous)`); capsules and circles
/// are the only exception.
nonisolated enum Radius {
    /// Cards and rows.
    static let card: CGFloat = 20
    /// Sheets, panels, toasts and every other glass surface.
    static let glass: CGFloat = 24
}

nonisolated enum Spacing {
    /// Left and right margin of every screen.
    static let pageMargin: CGFloat = 20
    /// Between the status bar and the first thing on a screen.
    static let pageTop: CGFloat = 12
    /// Below a screen's header.
    static let header: CGFloat = 16
    /// Between two cards in a list.
    static let cardGap: CGFloat = 8
    /// Inside a card, on every side.
    static let cardPadding: CGFloat = 14
    /// Between two sections of a screen.
    static let section: CGFloat = 24
    /// Between two lines inside one card.
    static let line: CGFloat = 4
}
