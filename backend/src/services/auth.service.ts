import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';
import { JwtPayload } from '../types/auth.types.js';

export class AuthService {
  constructor(private prisma: PrismaClient) {}

  async validateUserCredentials(email: string, passwordPlain: string): Promise<JwtPayload | null> {
    const user = await this.prisma.user.findUnique({
      where: { email: email.toLowerCase().trim() },
      include: {
        clientAssignments: true,
      },
    });

    if (!user || !user.isActive) {
      return null;
    }

    const isPasswordValid = await bcrypt.compare(passwordPlain, user.passwordHash);
    if (!isPasswordValid) {
      return null;
    }

    // Kumpulkan seluruh client_id yang dapat diakses pengguna
    const clientIdsSet = new Set<string>();
    if (user.defaultClientId) {
      clientIdsSet.add(user.defaultClientId);
    }
    for (const assignment of user.clientAssignments) {
      clientIdsSet.add(assignment.clientId);
    }

    return {
      id: user.id,
      email: user.email,
      fullName: user.fullName,
      role: user.role,
      defaultClientId: user.defaultClientId,
      assignedClientIds: Array.from(clientIdsSet),
    };
  }

  async getUserProfile(userId: string): Promise<JwtPayload | null> {
    const user = await this.prisma.user.findUnique({
      where: { id: userId },
      include: {
        clientAssignments: true,
      },
    });

    if (!user || !user.isActive) {
      return null;
    }

    const clientIdsSet = new Set<string>();
    if (user.defaultClientId) {
      clientIdsSet.add(user.defaultClientId);
    }
    for (const assignment of user.clientAssignments) {
      clientIdsSet.add(assignment.clientId);
    }

    return {
      id: user.id,
      email: user.email,
      fullName: user.fullName,
      role: user.role,
      defaultClientId: user.defaultClientId,
      assignedClientIds: Array.from(clientIdsSet),
    };
  }
}
