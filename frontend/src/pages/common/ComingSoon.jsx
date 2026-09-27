import { Card, Result } from 'antd'
import { ToolOutlined } from '@ant-design/icons'
import PageHeader from '../../components/PageHeader'

/** Placeholder for modules whose API is ready but whose screens are not built yet. */
export default function ComingSoon({ title }) {
  return (
    <>
      <PageHeader title={title} />
      <Card>
        <Result
          icon={<ToolOutlined style={{ color: '#1e88e5' }} />}
          title={`${title} screens are coming next`}
          subTitle="The API for this module is ready and can be used from the API documentation (/docs)."
        />
      </Card>
    </>
  )
}
