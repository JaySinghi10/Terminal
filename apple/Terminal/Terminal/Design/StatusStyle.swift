import SwiftUI

/// What a piece of a status line is saying, which decides its colour. This is
/// the only place the colour rule lives: green for live, amber for late or at
/// risk, red for cancelled, and grey for everything else.
nonisolated enum StatusTone: CaseIterable, Sendable {
    /// In the air, or a running countdown.
    case live
    /// Delayed, a late figure, diverted, a connection at risk.
    case late
    /// Cancelled.
    case cancelled
    /// The word "scheduled".
    case scheduled
    /// The word "landed".
    case landed
    /// Early figures, "updated" ages, the phone's own time, "no update".
    case quiet

    var rgba: RGBA {
        switch self {
        case .live: Palette.green
        case .late: Palette.amber
        case .cancelled: Palette.red
        case .scheduled: Ink.secondary.rgba
        case .landed: Ink.tertiary.rgba
        case .quiet: Ink.quaternary.rgba
        }
    }

    var color: Color { rgba.color }
}

extension FlightStatus {
    /// The tone of the status word itself.
    ///
    /// "No update" (stale) is grey: missing data is neither late nor at risk.
    nonisolated var tone: StatusTone {
        switch self {
        case .active: .live
        case .delayed, .diverted: .late
        case .cancelled: .cancelled
        case .scheduled: .scheduled
        case .landed: .landed
        case .stale: .quiet
        }
    }
}
