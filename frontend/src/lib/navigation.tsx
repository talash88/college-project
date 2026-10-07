import { ReactNode, SVGAttributes } from 'react';
import type { UserRole } from '@/types/api';

export interface NavItem {
  label: string;
  href: string;
  icon: ReactNode;
  enabled: boolean;
}

export interface NavSection {
  title: string | null;
  items: NavItem[];
}

interface NavIconProps extends SVGAttributes<SVGSVGElement> {}

function DashboardIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
    </svg>
  );
}

function ReportProblemIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3m0 0v3m0-3h3m-3 0H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

function MyReportsIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );
}

function AssignedProblemsIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
    </svg>
  );
}

function NotificationsIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
    </svg>
  );
}

function KnowledgeRepositoryIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
    </svg>
  );
}

function AnalyticsIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  );
}

function AdministrationIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function ProfileIcon(props: NavIconProps) {
  return (
    <svg {...props} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
    </svg>
  );
}

function dashboardItem(): NavItem {
  return {
    label: 'Dashboard',
    href: '/dashboard',
    icon: <DashboardIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function profileItem(): NavItem {
  return {
    label: 'Profile',
    href: '/profile',
    icon: <ProfileIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function reportProblemItem(): NavItem {
  return {
    label: 'Report Problem',
    href: '/problems/new',
    icon: <ReportProblemIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function myReportsItem(): NavItem {
  return {
    label: 'My Reports',
    href: '/problems',
    icon: <MyReportsIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function administrationItem(): NavItem {
  return {
    label: 'Administration',
    href: '/admin/problems',
    icon: <AdministrationIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function duplicatesItem(): NavItem {
  return {
    label: 'Duplicates',
    href: '/admin/duplicates',
    icon: <MyReportsIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function analyticsItem(): NavItem {
  return {
    label: 'Analytics',
    href: '/analytics',
    icon: <AnalyticsIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function assignedProblemsItem(): NavItem {
  return {
    label: 'Assigned Problems',
    href: '/assigned',
    icon: <AssignedProblemsIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function mentoredProblemsItem(): NavItem {
  return {
    label: 'Mentored Problems',
    href: '/mentored',
    icon: <AssignedProblemsIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function knowledgeItem(): NavItem {
  return {
    label: 'Knowledge Repository',
    href: '/knowledge',
    icon: <KnowledgeRepositoryIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function knowledgeAdminItem(): NavItem {
  return {
    label: 'Knowledge Admin',
    href: '/admin/knowledge',
    icon: <KnowledgeRepositoryIcon className="w-5 h-5" />,
    enabled: true,
  };
}

function notificationsItem(): NavItem {
  return {
    label: 'Notifications',
    href: '/notifications',
    icon: <NotificationsIcon className="w-5 h-5" />,
    enabled: true,
  };
}

/** Role-aware navigation. Auth/Profile work now; future modules stay disabled. */
export function getNavForRole(role: UserRole | null): NavSection[] {
  // Every authenticated role can report problems and view their own reports.
  const problemsSection: NavSection = {
    title: 'Problems',
    items: [reportProblemItem(), myReportsItem()],
  };
  const knowledgeSection: NavSection = {
    title: 'Knowledge',
    items: [knowledgeItem()],
  };

  switch (role) {
    case 'REPORTER':
      // Report Problem + My Reports already enabled above.
      break;
    case 'SOLVER':
      problemsSection.items.push(assignedProblemsItem());
      break;
    case 'MENTOR':
      problemsSection.items.push(mentoredProblemsItem());
      break;
    case 'ADMIN':
      problemsSection.items.push(
        administrationItem(),
        duplicatesItem(),
        knowledgeAdminItem(),
        analyticsItem()
      );
      // Admins have no separate Teams section item beyond the shared one.
      break;
    default:
      problemsSection.items = [];
      break;
  }

  const sections: NavSection[] = [
    { title: 'Core', items: [dashboardItem(), ...(role ? [notificationsItem()] : [])] },
  ];
  if (problemsSection.items.length > 0) {
    sections.push(problemsSection);
  }
  sections.push(knowledgeSection);
  sections.push({ title: 'Account', items: [profileItem()] });
  return sections;
}

/** @deprecated Use getNavForRole instead. Kept for backwards compatibility. */
export const NAV_ITEMS: NavSection[] = getNavForRole(null);
