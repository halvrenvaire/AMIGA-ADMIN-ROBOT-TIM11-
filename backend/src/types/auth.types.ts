import { UserRole } from '@prisma/client';

export interface JwtPayload {
  id: string;
  email: string;
  fullName: string;
  role: UserRole;
  defaultClientId: string | null;
  assignedClientIds: string[];
}

declare module '@fastify/jwt' {
  interface FastifyJWT {
    payload: JwtPayload;
    user: JwtPayload;
  }
}
