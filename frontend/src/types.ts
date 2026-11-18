/** Public identity returned by the API; password hashes are never sent. */
export interface User {
  id: string;
  name: string;
  email: string;
  role: string;
  portfolioAccess: string[];
  status: string;
  defaultLandingPage: 'dashboard' | 'applications' | null;
  mustChangePassword: boolean;
}

/** The login exchange returns a bearer token and public identity. */
export interface LoginResponse { token: string; user: User }

/** Editable application inventory attributes. */
export interface ApplicationFields {
  name: string; description: string; portfolioId: string; productArea: string;
  businessOwner: string; technologyOwner: string; etsOwner: string;
  criticality: 'Low' | 'Medium' | 'High' | 'Critical'; tier: number;
  lifecycleStatus: 'Active' | 'Deprecated' | 'Retired'; technologyStack: string;
  repositoryLink: string | null; pipelineLink: string | null;
  applicationHealthScore: number; qualityScore: number; automationCoverage: number;
  unitTestCoverage: number; openDefects: number; openCriticalDefects: number;
  riskLevel: 'Low' | 'Medium' | 'High';
}
export interface Application extends ApplicationFields { id: string; portfolioName: string; createdAt: string; updatedAt: string }
export interface Page<T> { items: T[]; total: number; offset: number; limit: number }

export interface AdminUser extends User { managerName: string | null; vendorIndicator: boolean; lastLogin: string | null }
export interface AdminRole { id: string; name: string; description: string; permissions: string[] }
export interface AuditEvent { id: string; timestamp: string; userId: string | null; userName: string; action: string; entityType: string; entityId: string | null; details: string }

export interface InsightPortfolio { id: string; name: string; owner: string; productArea: string; status: string; applicationCount: number; qualityScore: number | null; applicationsAtRisk: number }
export interface ExecutiveMetrics { enterpriseQualityScore: number | null; applicationHealthScore: number | null; automationMaturityScore: number | null; openCriticalDefects: number; applicationsAtRisk: number; totalApplications: number; totalPortfolios: number; portfolios: InsightPortfolio[] }
