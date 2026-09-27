// White base with light-blue accents.
// Buttons use a slightly deeper light blue so white text on them stays readable.
export const colors = {
  primary: '#1e88e5',
  primaryDark: '#1565c0',
  lightBlue: '#e3f2fd',
  lightBlueBorder: '#bbdefb',
  page: '#f5f9fe',
  white: '#ffffff',
  text: '#1f2d3d',
  muted: '#6b7c93',
}

export const theme = {
  token: {
    colorPrimary: colors.primary,
    colorInfo: colors.primary,
    colorLink: colors.primary,
    colorBgLayout: colors.page,
    colorBgContainer: colors.white,
    colorTextBase: colors.text,
    colorBorderSecondary: '#e6eef7',
    borderRadius: 8,
    fontFamily:
      "'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif",
  },
  components: {
    Layout: {
      siderBg: colors.white,
      headerBg: colors.white,
      bodyBg: colors.page,
      triggerBg: colors.lightBlue,
      triggerColor: colors.primaryDark,
    },
    Menu: {
      itemBg: colors.white,
      subMenuItemBg: colors.white,
      itemSelectedBg: colors.lightBlue,
      itemSelectedColor: colors.primaryDark,
      itemHoverBg: '#f0f7fe',
    },
    Card: {
      headerBg: colors.white,
    },
    Table: {
      headerBg: '#f0f7fe',
      headerColor: colors.primaryDark,
      rowHoverBg: '#f7fbff',
    },
  },
}
