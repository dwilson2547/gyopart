export class Feedback {
    
    name: string;
    email: string;
    comments: string;

    constructor(name: string, email: string, comments: string) {
        this.name = name;
        this.email = email;
        this.comments = comments;
    }

    toString() {
        return JSON.stringify(this)
    }
}