import SwiftUI

extension View {
    /// A card on the page: surface 1, radius 20, continuous corners. The padding
    /// is 14 on every side unless a caller needs a different shape, such as a
    /// button.
    func cardSurface(
        horizontal: CGFloat = Spacing.cardPadding,
        vertical: CGFloat = Spacing.cardPadding
    ) -> some View {
        padding(.horizontal, horizontal)
            .padding(.vertical, vertical)
            .background(
                Palette.surface1.color,
                in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
            )
    }
}
