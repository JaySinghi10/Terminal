#if DEBUG
import SwiftUI

/// The palette, the ink scale and the type scale on one page, for reviewing the
/// design system in Xcode's canvas. Debug only; nothing in the app shows it.
struct DesignPreview: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.section) {
                group("Surfaces") {
                    swatch("page #050505", Palette.page)
                    swatch("surface 1, white 0.045", Palette.surface1)
                    swatch("surface 2, white 0.08", Palette.surface2)
                    swatch("cancelled surface", Palette.cancelledSurface)
                    swatch("diverted surface", Palette.divertedSurface)
                }

                group("Accent and status") {
                    swatch("green, live or actionable", Palette.green)
                    swatch("amber, late or at risk", Palette.amber)
                    swatch("red, cancelled", Palette.red)
                }

                group("Ink") {
                    ForEach(Ink.allCases, id: \.self) { ink in
                        Text("\(String(describing: ink)) \(ink.alpha, format: .number)")
                            .textStyle(.body)
                            .foregroundStyle(ink.color)
                    }
                }

                group("Type scale") {
                    ForEach(TextStyle.allCases, id: \.self) { style in
                        Text("\(String(describing: style)) \(Int(style.size)) BA178 London")
                            .textStyle(style)
                            .foregroundStyle(Ink.primary.color)
                            .lineLimit(1)
                    }
                }
            }
            .padding(Spacing.pageMargin)
        }
        .background(Palette.page.color.ignoresSafeArea())
    }

    private func group<Content: View>(
        _ title: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: Spacing.cardGap) {
            Text(title)
                .textStyle(.label)
                .foregroundStyle(Ink.quaternary.color)
            content()
        }
    }

    private func swatch(_ name: String, _ colour: RGBA) -> some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(colour.color)
                .frame(width: 44, height: 28)
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .stroke(Palette.hairline.color)
                )
            Text(name)
                .textStyle(.caption)
                .foregroundStyle(Ink.tertiary.color)
        }
    }
}

#Preview {
    DesignPreview()
}
#endif
