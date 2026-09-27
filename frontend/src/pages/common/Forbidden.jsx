import { Button, Result } from 'antd'
import { Link } from 'react-router-dom'

export default function Forbidden() {
  return (
    <Result
      status="403"
      title="No access"
      subTitle="You do not have permission to open this page. Ask an administrator if you need it."
      extra={
        <Link to="/">
          <Button type="primary">Go to the dashboard</Button>
        </Link>
      }
    />
  )
}
