import { Link } from "react-router-dom";
import { ArrowLeft, Compass, ScanLine } from "lucide-react";
import EmptyState from "../components/EmptyState";

export default function NotFound() {
  return (
    <div className="panel">
      <EmptyState
        icon={Compass}
        title="This page does not exist"
        description="The address may be mistyped, or the page may have moved. Your scans and account data are unaffected."
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Link to="/" className="btn">
              <ArrowLeft size={15} /> Back home
            </Link>
            <Link to="/scan" className="btn btn-primary">
              <ScanLine size={15} /> Run a scan
            </Link>
          </div>
        }
      />
    </div>
  );
}
