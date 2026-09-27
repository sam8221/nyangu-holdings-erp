import { Card, Typography } from 'antd'
import { colors } from '../../theme'

/** Centred card on a white-to-light-blue background, shared by the sign-in pages. */
export default function AuthShell({ title, subtitle, children }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 16,
        background: `linear-gradient(160deg, ${colors.white} 0%, ${colors.lightBlue} 100%)`,
      }}
    >
      <div style={{ width: '100%', maxWidth: 400 }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div
            style={{
              width: 52,
              height: 52,
              margin: '0 auto 12px',
              borderRadius: 12,
              background: colors.primary,
              color: colors.white,
              display: 'grid',
              placeItems: 'center',
              fontSize: 24,
              fontWeight: 700,
            }}
          >
            N
          </div>
          <Typography.Title level={3} style={{ margin: 0, color: colors.primaryDark }}>
            Nyangu Holdings ERP
          </Typography.Title>
        </div>
        <Card
          style={{ boxShadow: '0 8px 24px rgba(30, 136, 229, 0.12)', borderColor: colors.lightBlueBorder }}
        >
          <Typography.Title level={4} style={{ marginTop: 0 }}>
            {title}
          </Typography.Title>
          {subtitle && (
            <Typography.Paragraph type="secondary" style={{ marginTop: -4 }}>
              {subtitle}
            </Typography.Paragraph>
          )}
          {children}
        </Card>
      </div>
    </div>
  )
}
